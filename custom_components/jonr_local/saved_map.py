"""Saved-map mode: serve a locally stored copy of the robot's map.

The xtl robot cannot hand its map over the LAN (it only names the KS3 cloud
file — docs/MIOT_SPEC.md), so the fork imports that file ONCE
(tools/dump_map.py on a PC, pushed through the ``jonr_local.import_map``
service) and keeps it in HA storage. At runtime nothing here touches the
network: the copy is decoded and rendered with the integration's own
xtl_map pipeline, and fed to the platforms through the same
``runtime_data.map`` interface the cloud coordinator offers (``.data`` =
MapResult, ``.map_list_meta``, ``.device``, ``async_request_refresh``).
"""
from __future__ import annotations

import collections
import hashlib
import logging
import time
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .device import XtlVacuumDevice
from .map import MapResult
from .spec.profiles.xtl import xtl_parse_map_infos_catalog, xtl_parse_map_infos_file
from .xtl_map import decode_map_file, render_xtl_map

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
_STORAGE_KEY_FMT = f"{DOMAIN}_saved_map_{{entry_id}}"

# Entry-data key the config flow uses to hand over a map downloaded during
# setup; imported into the Store on first load, then removed from the entry.
PENDING_MAP_KEY = "pending_map"
ISSUE_MAP_MISSING = "saved_map_missing_{entry_id}"

# 17.53 payload keys -> the `prefer` keys the map file carries per room.
_PREFER_FROM_PAYLOAD = {"K": "mode", "F": "wind", "W": "water", "C": "count", "D": "drag"}


@dataclass
class SavedMapView:
    """Everything the platforms need, derived (pure) from the stored files."""

    result: MapResult
    catalog: list[dict]
    room_names: dict[int, str]
    room_area_m2: dict[int, float]
    map_name: str | None
    sha256: str
    extra: dict = field(default_factory=dict)


def build_view(raw_map: bytes, raw_infos: bytes | None = None,
               prefer_overrides: dict[str, dict] | None = None) -> SavedMapView:
    """Decode + render a saved map file. Pure (no HA, no network).

    Raises ValueError when the file holds no readable map.
    """
    rendered = render_xtl_map(raw_map)
    decoded = decode_map_file(raw_map)
    if rendered is None or decoded is None:
        raise ValueError("the file holds no readable xtl map")
    result = MapResult(**rendered)
    map_id = result.map_id

    names = xtl_parse_map_infos_file(raw_infos) if raw_infos else {}
    catalog = xtl_parse_map_infos_catalog(raw_infos) if raw_infos else []
    map_name = names.get(map_id) if map_id is not None else None
    if not catalog and map_id is not None:
        catalog = [{"name": map_name, "id": map_id, "cur": 1}]

    rooms = result.attributes.get("rooms") or {}
    for rid, pref in (prefer_overrides or {}).items():
        if rid in rooms:
            rooms[rid]["prefer"] = {**(rooms[rid].get("prefer") or {}), **pref}

    cells = collections.Counter(decoded["raster"])
    cell_m = float(decoded["resolution_cm"]) / 100.0
    room_area = {int(rid): round(cells.get(int(rid), 0) * cell_m * cell_m, 1) for rid in rooms}
    room_names = {int(rid): str(r.get("name") or "") for rid, r in rooms.items()}

    result.maps = [{**result.vector, "map_id": map_id, "map_name": map_name, "active": True}]
    return SavedMapView(
        result=result, catalog=catalog, room_names=room_names,
        room_area_m2=room_area, map_name=map_name,
        sha256=hashlib.sha256(raw_map).hexdigest(),
    )


def download_map_once(cloud, server: str, did: str, device: XtlVacuumDevice) -> tuple[str, str | None]:
    """Blocking one-shot map download (setup / options flow only, never at runtime).

    The robot names its map files over the LAN (17.12 map, 17.13 catalogue —
    it may stay blocked from the internet: the files were uploaded earlier);
    the logged-in cloud session mints signed URLs and downloads them once.
    Returns (map_raw, map_infos_raw) as text; raises ValueError with a
    user-facing reason.
    """
    try:
        map_obj = device.map_obj_name()
        device.map_list()                      # stashes the catalogue file name
    except Exception as err:  # noqa: BLE001
        raise ValueError(f"the robot did not answer over the LAN ({err})") from err
    if not map_obj:
        raise ValueError("the robot has no map yet — map your home in the Mi Home app first")
    infos_obj = device.last_map_infos_file

    def fetch(obj: str) -> bytes | None:
        url = cloud.map_url(server, did, obj, "get_interim_file_url_pro", raw_obj=True)
        return cloud.download(url) if url else None

    raw_map = fetch(map_obj)
    if not raw_map:
        raise ValueError("Xiaomi cloud has no map file for this robot (open the map once in "
                         "Mi Home while the robot is online, then try again)")
    raw_infos = fetch(infos_obj) if infos_obj else None
    build_view(raw_map, raw_infos)             # validates; raises ValueError
    return raw_map.decode("utf-8"), raw_infos.decode("utf-8") if raw_infos else None


class SavedMapCoordinator(DataUpdateCoordinator[MapResult]):
    """Serves the imported map copy. Never polls, never opens a socket."""

    # Read by select.py / vacuum.py to switch off cloud-only behaviour.
    is_saved_map = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 device: XtlVacuumDevice, control) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}:saved_map", update_interval=None)
        self.entry = entry
        self._device = device
        self._control = control
        self._store: Store = Store(hass, STORAGE_VERSION,
                                   _STORAGE_KEY_FMT.format(entry_id=entry.entry_id))
        self._stored: dict = {}
        self._view: SavedMapView | None = None

    # --- interface shared with JonrMapCoordinator --------------------------
    @property
    def device(self) -> XtlVacuumDevice:
        return self._device

    @property
    def control(self):
        return self._control

    @property
    def map_list_meta(self) -> list[dict]:
        return self._view.catalog if self._view else []

    # --- saved-map specifics ----------------------------------------------
    @property
    def view(self) -> SavedMapView | None:
        return self._view

    @property
    def room_ids(self) -> set[int]:
        return set(self._view.room_names) if self._view else set()

    @property
    def imported_at(self) -> str | None:
        return self._stored.get("imported_at")

    def _issue_id(self) -> str:
        return ISSUE_MAP_MISSING.format(entry_id=self.entry.entry_id)

    async def async_load(self) -> None:
        """Load the stored copy (if any) and render it once."""
        self._stored = await self._store.async_load() or {}
        pending = self.entry.data.get(PENDING_MAP_KEY)
        if isinstance(pending, dict) and pending.get("map_raw"):
            # Map downloaded by the config flow: move it into the Store and
            # drop it from the entry data (it does not belong there long-term).
            try:
                await self.async_import(pending["map_raw"], pending.get("map_infos_raw"),
                                        "config flow (one-time cloud download)")
            except ValueError as err:
                _LOGGER.error("Map handed over by the setup flow is unreadable: %s", err)
            data = {k: v for k, v in self.entry.data.items() if k != PENDING_MAP_KEY}
            self.hass.config_entries.async_update_entry(self.entry, data=data)
            if self._view is not None:
                return
        if self._stored.get("map_raw"):
            try:
                self._view = await self.hass.async_add_executor_job(self._build)
            except ValueError as err:
                _LOGGER.error("Saved map is unreadable (%s) — import it again", err)
                self._view = None
        if self._view is None:
            # Expected right after setup: not an error, so no coordinator
            # refresh (it would log UpdateFailed at ERROR). Entities simply
            # stay unavailable until jonr_local.import_map runs.
            _LOGGER.warning(
                "No saved map yet — use Configure → 'Download the map from your "
                "Xiaomi account' on the JONR Local integration")
            ir.async_create_issue(
                self.hass, DOMAIN, self._issue_id(), is_fixable=False,
                severity=ir.IssueSeverity.WARNING, translation_key="saved_map_missing",
                learn_more_url="https://github.com/Krystianpoprostu/jonr-local/blob/main/docs/LOCAL_MODE.md",
            )
            self.last_update_success = False
            return
        await self.async_refresh()

    def _build(self) -> SavedMapView:
        raw_infos = self._stored.get("map_infos_raw")
        return build_view(
            self._stored["map_raw"].encode("utf-8"),
            raw_infos.encode("utf-8") if raw_infos else None,
            self._stored.get("prefer_overrides"),
        )

    async def _async_update_data(self) -> MapResult:
        if self._view is None:
            raise UpdateFailed(
                "No saved map yet — run tools/dump_map.py and the jonr_local.import_map service")
        return self._view.result

    async def async_import(self, map_raw: str, map_infos_raw: str | None,
                           source: str | None = None) -> dict:
        """Validate, persist and serve a new map copy. Returns a summary."""
        candidate = {
            "map_raw": map_raw,
            "map_infos_raw": map_infos_raw,
            "imported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source": source or "import_map service",
            "prefer_overrides": {},
        }
        previous, self._stored = self._stored, candidate
        try:
            view = await self.hass.async_add_executor_job(self._build)
        except ValueError:
            self._stored = previous
            raise
        await self._store.async_save(candidate)
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id())
        old_rooms = set(self._view.room_names) if self._view else set()
        self._view = view
        self.async_set_updated_data(view.result)
        return {
            "map_id": view.result.map_id,
            "map_name": view.map_name,
            "rooms": {str(k): v for k, v in sorted(view.room_names.items())},
            "room_area_m2": {str(k): v for k, v in sorted(view.room_area_m2.items())},
            "sha256": view.sha256,
            "imported_at": candidate["imported_at"],
            "rooms_added": sorted(set(view.room_names) - old_rooms) if old_rooms else [],
            "rooms_removed": sorted(old_rooms - set(view.room_names)),
        }

    async def async_note_room_prefer(self, prefs: list[dict]) -> None:
        """Mirror a successful 17.53 per-room write into the saved copy, so
        the room panel (and later merges) do not resurrect stale values —
        the robot cannot re-upload the map while offline."""
        if not self._view:
            return
        overrides: dict = self._stored.setdefault("prefer_overrides", {})
        rooms = self._view.result.attributes.get("rooms") or {}
        for p in prefs:
            rid = str(p.get("R"))
            mapped = {v: p[k] for k, v in _PREFER_FROM_PAYLOAD.items() if k in p}
            if not mapped:
                continue
            overrides[rid] = {**overrides.get(rid, {}), **mapped}
            if rid in rooms:
                rooms[rid]["prefer"] = {**(rooms[rid].get("prefer") or {}), **mapped}
        await self._store.async_save(self._stored)
        self.async_set_updated_data(self._view.result)
