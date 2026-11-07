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
import json
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


def catalog_map_files(raw_infos: bytes | str | None) -> dict[int, bytes]:
    """Every saved floor in the map-catalogue file, as a self-contained map file.

    The catalogue (17.13's KS3 file) carries, per saved map, the same parts the
    current-map file has — raster (mapData), rooms (areas), virtual walls, mop
    walls, carpets, sills — just without the live trace/pose. Rebuilding the
    9-field envelope lets xtl_map render any floor offline (checked against the
    real current-map file: identical rooms, walls, calibration and dock).
    """
    if not raw_infos:
        return {}
    try:
        cat = json.loads(raw_infos)
    except ValueError:
        return {}
    if isinstance(cat, dict):
        cat = next((v for v in cat.values() if isinstance(v, list)), [])
    out: dict[int, bytes] = {}
    for m in cat if isinstance(cat, list) else []:
        if not isinstance(m, dict) or not m.get("mapData"):
            continue
        try:
            map_id = int(m.get("mapId"))
        except (TypeError, ValueError):
            continue
        if map_id == 0 or m.get("saved", 1) == 0:
            continue            # 0 / unsaved = the robot's live draft, never a target
        fields = [m["mapData"], "", "", m.get("areas") or "[]", m.get("virtualWalls") or "",
                  m.get("mopWalls") or "", m.get("carpet") or "", m.get("thres") or "",
                  m.get("carpetprefer") or []]
        out[map_id] = json.dumps({"mapId": map_id, "fields": fields}).encode()
    return out


def build_views(raw_map: bytes | None, raw_infos: bytes | None,
                prefer_by_map: dict[str, dict] | None = None,
                ) -> tuple[dict[int, SavedMapView], int | None]:
    """All saved floors -> {map_id: view}, plus the map the robot reported as
    current. The current-map file wins for its own id (it carries the trace).
    Raises ValueError when nothing is readable."""
    files = catalog_map_files(raw_infos)
    current_id = None
    if raw_map:
        decoded = decode_map_file(raw_map)
        if decoded is not None and isinstance(decoded.get("map_id"), int):
            current_id = decoded["map_id"]
            files[current_id] = raw_map
    if not files:
        raise ValueError("the files hold no readable xtl map")
    catalog = xtl_parse_map_infos_catalog(raw_infos) if raw_infos else []
    cur_from_catalog = next((m["id"] for m in catalog if m.get("cur")), None)
    views: dict[int, SavedMapView] = {}
    for map_id, data in files.items():
        try:
            views[map_id] = build_view(data, raw_infos, (prefer_by_map or {}).get(str(map_id)))
        except ValueError:
            if map_id == current_id:
                raise
            _LOGGER.warning("Saved map %s in the catalogue is unreadable — skipped", map_id)
    if not views:
        raise ValueError("the files hold no readable xtl map")
    active = current_id if current_id in views else cur_from_catalog
    if active not in views:
        active = next(iter(views))
    return views, active


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
    """Serves the imported map copy (every saved floor). Never polls, never
    opens a socket. The active floor is tracked here: the robot exposes no
    readable "current map" property over the LAN, and its catalogue file only
    updates in the cloud, so the last switch made through Home Assistant (or
    the catalogue's current map at import time) is the truth."""

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
        self._views: dict[int, SavedMapView] = {}
        self._active: int | None = None

    # --- interface shared with JonrMapCoordinator --------------------------
    @property
    def device(self) -> XtlVacuumDevice:
        return self._device

    @property
    def control(self):
        return self._control

    @property
    def map_list_meta(self) -> list[dict]:
        """[{name, id, cur, saved}] for every saved floor; cur = active one."""
        return [{"name": v.map_name, "id": mid, "cur": 1 if mid == self._active else 0, "saved": 1}
                for mid, v in sorted(self._views.items())]

    # --- saved-map specifics ----------------------------------------------
    @property
    def view(self) -> SavedMapView | None:
        return self._views.get(self._active) if self._active is not None else None

    @property
    def maps(self) -> dict[int, str]:
        return {mid: (v.map_name or f"Map {mid}") for mid, v in sorted(self._views.items())}

    @property
    def active_map_id(self) -> int | None:
        return self._active

    @property
    def floor_rooms(self) -> dict[int, tuple[str, dict[int, str]]]:
        """{map_id: (floor name, {room id: room name})} for every saved floor."""
        return {mid: (v.map_name or f"Map {mid}", dict(v.room_names))
                for mid, v in sorted(self._views.items())}

    @property
    def room_ids(self) -> set[int]:
        return set(self.view.room_names) if self.view else set()

    @property
    def imported_at(self) -> str | None:
        return self._stored.get("imported_at")

    def _issue_id(self) -> str:
        return ISSUE_MAP_MISSING.format(entry_id=self.entry.entry_id)

    def _compose(self) -> MapResult | None:
        """Active floor's result, with `.maps` listing every floor (card pages)."""
        view = self.view
        if view is None:
            return None
        view.result.maps = [
            {**v.result.vector, "map_id": mid, "map_name": v.map_name, "active": mid == self._active}
            for mid, v in sorted(self._views.items())
        ]
        return view.result

    def _prefer_by_map(self, current_id: int | None = None) -> dict:
        """Per-floor 17.53 overrides; a pre-0.3 store kept one flat dict for the
        single map it had — attach it to that map."""
        by_map = self._stored.get("prefer_by_map")
        if by_map is None:
            legacy = self._stored.get("prefer_overrides") or {}
            by_map = {str(current_id): legacy} if legacy and current_id is not None else {}
            self._stored["prefer_by_map"] = by_map
        return by_map

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
            if self._views:
                return
        if self._stored.get("map_raw") or self._stored.get("map_infos_raw"):
            try:
                views, current = await self.hass.async_add_executor_job(self._build)
            except ValueError as err:
                _LOGGER.error("Saved map is unreadable (%s) — import it again", err)
            else:
                self._views = views
                stored_active = self._stored.get("active_map_id")
                self._active = stored_active if stored_active in views else current
        if not self._views:
            # Expected right after setup: not an error, so no coordinator
            # refresh (it would log UpdateFailed at ERROR). Entities simply
            # stay unavailable until a map is imported.
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

    def _build(self) -> tuple[dict[int, SavedMapView], int | None]:
        raw_map = self._stored.get("map_raw")
        raw_infos = self._stored.get("map_infos_raw")
        raw_map_b = raw_map.encode("utf-8") if raw_map else None
        current = None
        if raw_map_b:
            decoded = decode_map_file(raw_map_b)
            current = decoded.get("map_id") if decoded else None
        return build_views(raw_map_b, raw_infos.encode("utf-8") if raw_infos else None,
                           self._prefer_by_map(current))

    async def _async_update_data(self) -> MapResult:
        result = self._compose()
        if result is None:
            raise UpdateFailed("No saved map yet — download it via Configure on the integration")
        return result

    async def async_import(self, map_raw: str, map_infos_raw: str | None,
                           source: str | None = None) -> dict:
        """Validate, persist and serve a new map copy (all saved floors).
        Returns a summary of the active floor plus the list of floors."""
        candidate = {
            "map_raw": map_raw,
            "map_infos_raw": map_infos_raw,
            "imported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source": source or "import_map service",
            "prefer_by_map": {},
        }
        previous, self._stored = self._stored, candidate
        try:
            views, current = await self.hass.async_add_executor_job(self._build)
        except ValueError:
            self._stored = previous
            raise
        old_rooms = set(self.view.room_names) if self.view else set()
        # The robot's current map (from this download) is the truth for the
        # active floor; it is what Mi Home shows as in use right now.
        self._views, self._active = views, current
        candidate["active_map_id"] = current
        await self._store.async_save(candidate)
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id())
        self.async_set_updated_data(self._compose())
        view = self.view
        return {
            "map_id": self._active,
            "map_name": view.map_name,
            "maps": {str(k): v for k, v in self.maps.items()},
            "rooms": {str(k): v for k, v in sorted(view.room_names.items())},
            "room_area_m2": {str(k): v for k, v in sorted(view.room_area_m2.items())},
            "sha256": view.sha256,
            "imported_at": candidate["imported_at"],
            "rooms_added": sorted(set(view.room_names) - old_rooms) if old_rooms else [],
            "rooms_removed": sorted(old_rooms - set(view.room_names)),
        }

    async def async_set_active(self, map_id: int) -> None:
        """Record that the robot now works on `map_id` (after a successful
        local switch-map) and serve that floor."""
        if map_id not in self._views:
            raise ValueError(f"map {map_id} is not in the saved copy")
        self._active = map_id
        self._stored["active_map_id"] = map_id
        await self._store.async_save(self._stored)
        self.async_set_updated_data(self._compose())

    async def async_note_room_prefer(self, prefs: list[dict]) -> None:
        """Mirror a successful 17.53 per-room write into the saved copy of the
        active floor, so the room panel (and later merges) do not resurrect
        stale values — the robot cannot re-upload the map while offline."""
        view = self.view
        if view is None:
            return
        overrides: dict = self._prefer_by_map().setdefault(str(self._active), {})
        rooms = view.result.attributes.get("rooms") or {}
        for p in prefs:
            rid = str(p.get("R"))
            mapped = {v: p[k] for k, v in _PREFER_FROM_PAYLOAD.items() if k in p}
            if not mapped:
                continue
            overrides[rid] = {**overrides.get(rid, {}), **mapped}
            if rid in rooms:
                rooms[rid]["prefer"] = {**(rooms[rid].get("prefer") or {}), **mapped}
        await self._store.async_save(self._stored)
        self.async_set_updated_data(self._compose())
