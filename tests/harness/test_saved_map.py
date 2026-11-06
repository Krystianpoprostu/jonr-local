"""Harness tests for the fork's fully local 'saved map' mode.

The map fixture is synthetic (no real home data): two rooms on a small raster.
pytest-homeassistant-custom-component disables sockets, so any cloud call the
mode might attempt would fail these tests outright; the cloud classes are
additionally patched to explode if they are ever constructed.
"""
from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jonr_local.const import (
    CONF_HOST, CONF_MAC, CONF_MAP_MODE, CONF_MODEL, CONF_TOKEN, DOMAIN,
    EVENT_CLEAN_FINISHED, MAP_MODE_SAVED,
)
from custom_components.jonr_local.device import VacuumStatus

MODEL = "xtl.vacuum.xm2216"


def _lz4_literal(data: bytes) -> bytes:
    n = len(data)
    out = bytearray([min(n, 15) << 4])
    if n >= 15:
        rest = n - 15
        while rest >= 255:
            out.append(255)
            rest -= 255
        out.append(rest)
    return bytes(out + data)


def synthetic_map(map_id: int = 3) -> str:
    """20x10 raster: walls (1) around two rooms, room_id 3 (left) and 4 (right)."""
    w, h = 20, 10
    raster = bytearray()
    for y in range(h):
        for x in range(w):
            if x in (0, w - 1) or y in (0, h - 1) or x == 10:
                raster.append(1)
            else:
                raster.append(3 if x < 10 else 4)
    map_data = {"map": base64.b64encode(_lz4_literal(bytes(raster))).decode(),
                "lz4Len": len(raster), "width": w, "height": h,
                "xMin": 400, "yMax": 300, "resolution": 5,
                "chargePos": {"x": 305, "y": 395, "a": 0}}
    areas = [
        {"id": 1, "name": "Room A", "type": "1", "neibs": "2", "centerX": 405, "centerY": 305,
         "prefer": {"mode": 0, "water": 1, "wind": 1, "count": 1, "order": 0, "drag": 1}},
        {"id": 2, "name": "Room B", "type": "4", "neibs": "1", "centerX": 405, "centerY": 315,
         "prefer": {"mode": 0, "water": 1, "wind": 1, "count": 1, "order": 0, "drag": 1}},
    ]
    fields = [base64.b64encode(json.dumps(map_data).encode()).decode(), "", "",
              json.dumps(areas), "", "", "", "", "[]"]
    return json.dumps({"mapId": map_id, "fields": fields})


INFOS = json.dumps([{"mapId": 3, "name": "Test floor", "saved": 1, "status": 1}])


def _status(**kw) -> VacuumStatus:
    base = dict(activity="docked", raw_status=13, battery=100, fault=0, fan_speed_raw=1,
                water_level_raw=1, mode_raw=0, sweep_type_raw=None, repeat_raw=None,
                alarm_raw=None, volume_raw=80, main_brush_life=100, side_brush_life=100,
                filter_life=100, mop_life=100, dust_bag_life=None, detergent_life=None,
                clean_area=0, clean_time=0, robot_status_raw=1, clean_values_raw="[]",
                station_error_raw=0)
    base.update(kw)
    return VacuumStatus(**base)


@pytest.fixture
def no_cloud():
    """Any cloud construction is a test failure."""
    boom = MagicMock(side_effect=AssertionError("cloud used in saved-map mode"))
    with patch("custom_components.jonr_local.map_coordinator.XiaomiCloud", boom), \
         patch("custom_components.jonr_local.vacuum.XiaomiCloud", boom), \
         patch("custom_components.jonr_local.MiotMqttClient", boom):
        yield boom


@pytest.fixture
def miot():
    """Real XtlVacuumDevice over a mocked python-miio transport; status() is
    pinned for the whole test so polls never mark the entities unavailable
    (HA silently skips entity services on unavailable entities)."""
    with patch("custom_components.jonr_local.device.MiotDevice") as cls, \
         patch("custom_components.jonr_local.device.XtlVacuumDevice.status",
               return_value=_status()):
        yield cls.return_value


async def _setup(hass: HomeAssistant, miot) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, version=2, unique_id="aa:bb:cc:dd:ee:ff", data={
        CONF_HOST: "192.0.2.10", CONF_TOKEN: "0" * 32, CONF_MODEL: MODEL,
        CONF_MAC: "aa:bb:cc:dd:ee:ff", CONF_MAP_MODE: MAP_MODE_SAVED})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _ids(hass, platform):
    return [s.entity_id for s in hass.states.async_all(platform)]


async def test_saved_map_mode_end_to_end(hass: HomeAssistant, no_cloud, miot) -> None:
    entry = await _setup(hass, miot)
    assert entry.state is ConfigEntryState.LOADED
    rt = entry.runtime_data
    assert rt.mqtt is None
    assert getattr(rt.map, "is_saved_map", False)
    vac = _ids(hass, "vacuum")[0]
    cam = _ids(hass, "camera")[0]
    assert hass.states.get(cam).state == "unavailable"          # nothing imported yet
    sel = [s for s in _ids(hass, "select") if s.endswith("active_map")]
    assert sel and hass.states.get(sel[0]).state == "unavailable"   # no floors until a map is imported

    resp = await hass.services.async_call(
        DOMAIN, "import_map",
        {"entity_id": vac, "map_raw": synthetic_map(), "map_infos_raw": INFOS, "source": "test"},
        blocking=True, return_response=True)
    summary = resp[vac]
    assert summary["map_id"] == 3 and summary["map_name"] == "Test floor"
    assert summary["rooms"] == {"3": "Room A", "4": "Room B"}
    assert summary["room_area_m2"]["3"] > 0
    await hass.async_block_till_done()
    attrs = hass.states.get(cam).attributes
    assert set(attrs["rooms"]) == {"3", "4"}

    # Room cleaning: known ids go to the robot (17.1 type 3), unknown ids are refused.
    with patch("custom_components.jonr_local.device.time.sleep"):
        await hass.services.async_call(DOMAIN, "clean_segment",
                                       {"entity_id": vac, "segments": [4]}, blocking=True)
    sent = [c.args for c in miot.call_action_by.call_args_list]
    assert (17, 1, [{"did": "-", "piid": 8, "value": 3},
                    {"did": "-", "piid": 34, "value": "[4]"}]) in sent
    with pytest.raises(HomeAssistantError, match="not in the saved map"):
        await hass.services.async_call(DOMAIN, "clean_segment",
                                       {"entity_id": vac, "segments": [9]}, blocking=True)

    # 17.15 is never sent from a local entry (it breaks the robot's task, live 2026-11-06).
    miot.call_action_by.reset_mock()
    with pytest.raises(HomeAssistantError, match="Mi Home"):
        await hass.services.async_call(DOMAIN, "set_room_info",
                                       {"entity_id": vac, "room_id": 3, "name": "X"}, blocking=True)
    assert not [c for c in miot.call_action_by.call_args_list if c.args[:2] == (17, 15)]

    # Per-room preference write goes local (17.53) and is mirrored into the copy.
    await hass.services.async_call(DOMAIN, "set_room_clean_mode",
                                   {"entity_id": vac, "room_id": 3, "fan": 3}, blocking=True)
    assert any(c.args[:2] == (17, 53) for c in miot.call_action_by.call_args_list)
    await hass.async_block_till_done()
    assert hass.states.get(cam).attributes["rooms"]["3"]["prefer"]["wind"] == 3

    # refresh_map (the movement + cloud one) is refused with guidance.
    with pytest.raises(HomeAssistantError, match="dump_map"):
        await hass.services.async_call(DOMAIN, "refresh_map",
                                       {"entity_id": vac, "confirm_movement": True}, blocking=True)

    # The copy survives a reload (HA storage), still without any cloud object.
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    attrs = hass.states.get(cam).attributes
    assert set(attrs["rooms"]) == {"3", "4"}
    assert attrs["rooms"]["3"]["prefer"]["wind"] == 3
    no_cloud.assert_not_called()


async def test_clean_log_records_a_room_task(hass: HomeAssistant, no_cloud, miot) -> None:
    entry = await _setup(hass, miot)
    vac = _ids(hass, "vacuum")[0]
    await hass.services.async_call(DOMAIN, "import_map",
                                   {"entity_id": vac, "map_raw": synthetic_map()},
                                   blocking=True, return_response=True)
    events = []
    hass.bus.async_listen(EVENT_CLEAN_FINISHED, events.append)
    control = entry.runtime_data.control
    for snap in (
        _status(activity="cleaning", raw_status=7, robot_status_raw=8, clean_values_raw="[3,4]", clean_area=0),
        _status(activity="cleaning", raw_status=7, robot_status_raw=8, clean_values_raw="[3,4]", clean_area=1),
        _status(activity="returning", raw_status=12, robot_status_raw=8, clean_values_raw="[3,4]", clean_area=1),
        _status(activity="docked", raw_status=13, robot_status_raw=1, clean_values_raw="[]", clean_area=1),
    ):
        control.async_set_updated_data(snap)
    await hass.async_block_till_done()
    assert len(events) == 1
    rec = events[0].data
    assert rec["kind"] == "rooms" and rec["room_ids"] == [3, 4]
    assert rec["rooms"] == ["Room A", "Room B"]
    assert rec["area_m2"] == 1 and rec["dock_returns"] == 1 and rec["ended_on_dock"]
    sensor = [s for s in _ids(hass, "sensor") if s.endswith("last_clean")][0]
    assert hass.states.get(sensor).state == str(rec["coverage_pct"])


async def test_config_flow_local_map_creates_saved_entry(hass: HomeAssistant) -> None:
    from homeassistant.data_entry_flow import FlowResultType

    with patch("custom_components.jonr_local.config_flow._probe",
               return_value={"model": MODEL, "mac": "aa:bb:cc:dd:ee:01"}), \
         patch("custom_components.jonr_local.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert "local_map" in r["menu_options"]
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "local_map"})
        assert r["type"] is FlowResultType.FORM and r["step_id"] == "local_map"
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {CONF_HOST: "192.0.2.10", CONF_TOKEN: "0" * 32})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["title"] == "Jonr P20 Pro"
    assert r["data"][CONF_MAP_MODE] == MAP_MODE_SAVED
    assert "username" not in r["data"] and "service_token" not in r["data"]


# --- build_view: map parsing + room mapping on synthetic data -------------------
from custom_components.jonr_local.saved_map import build_view  # noqa: E402


def test_build_view_rooms_areas_and_names() -> None:
    v = build_view(synthetic_map().encode(), INFOS.encode())
    assert v.result.map_id == 3 and v.map_name == "Test floor"
    # room_id falls back to id + 2 when the file carries none (plugin rule)
    assert v.room_names == {3: "Room A", 4: "Room B"}
    # 8x9 floor cells each side of the wall at 5 cm -> 0.2 m²
    assert v.room_area_m2 == {3: 0.2, 4: 0.2}
    assert v.catalog == [{"name": "Test floor", "id": 3, "cur": 1}]
    assert v.result.maps[0]["active"] and v.result.maps[0]["map_name"] == "Test floor"
    cal = v.result.attributes["calibration_points"]
    assert len(cal) == 3 and all({"map", "vacuum"} <= set(p) for p in cal)


def test_build_view_without_catalogue_synthesises_one_map() -> None:
    v = build_view(synthetic_map(map_id=5).encode(), None)
    assert v.catalog == [{"name": None, "id": 5, "cur": 1}]
    assert v.map_name is None


def test_build_view_applies_prefer_overrides() -> None:
    v = build_view(synthetic_map().encode(), None, {"4": {"wind": 3, "water": 2}})
    p = v.result.attributes["rooms"]["4"]["prefer"]
    assert p["wind"] == 3 and p["water"] == 2 and p["mode"] == 0


def test_build_view_rejects_garbage() -> None:
    import pytest as _pytest

    for bad in (b"", b"{}", b"not json", json.dumps({"mapId": 1, "fields": ["x"]}).encode()):
        with _pytest.raises(ValueError):
            build_view(bad, None)


def test_explicit_room_id_wins_over_id_plus_two() -> None:
    raw = json.loads(synthetic_map())
    areas = json.loads(raw["fields"][3])
    areas[0]["room_id"] = 4          # explicit room_id must be honoured
    areas[1]["room_id"] = 3
    raw["fields"][3] = json.dumps(areas)
    v = build_view(json.dumps(raw).encode(), None)
    assert v.room_names == {4: "Room A", 3: "Room B"}


# --- v0.2.0: guided setup (Xiaomi account once -> fully local) -----------------
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.helpers import issue_registry as ir  # noqa: E402

from custom_components.jonr_local.saved_map import PENDING_MAP_KEY, download_map_once  # noqa: E402

ROBOT = {"name": "Robot", "did": "123", "model": MODEL, "mac": "aa:bb:cc:dd:ee:02",
         "localip": "192.0.2.20", "token": "1" * 32, "server": "de"}


class FakeCloud:
    """Stands in for XiaomiCloud: scripted login states, one robot, no network."""
    states: list = ["ok"]
    instances: list = []

    def __init__(self, username, password=""):
        self._states = list(FakeCloud.states)
        self.login_error = ""
        self.captcha_image = b""
        FakeCloud.instances.append(self)

    def begin_login(self):
        return self._states.pop(0)

    def submit_2fa(self, code):
        return self._states.pop(0)

    def submit_captcha(self, code):
        return self._states.pop(0)

    def list_vacuums(self):
        return [dict(ROBOT)]


def _patch_cloud(states):
    FakeCloud.states, FakeCloud.instances = states, []
    return patch("custom_components.jonr_local.config_flow.XiaomiCloud", FakeCloud)


async def _guided(hass, *, map_ok=True):
    dl = (patch("custom_components.jonr_local.config_flow.download_map_once",
                return_value=(synthetic_map(), INFOS)) if map_ok else
          patch("custom_components.jonr_local.config_flow.download_map_once",
                side_effect=ValueError("no map")))
    with _patch_cloud(["ok"]), dl, \
         patch("custom_components.jonr_local.config_flow._probe",
               return_value={"model": MODEL, "mac": ROBOT["mac"]}), \
         patch("custom_components.jonr_local.config_flow.XtlVacuumDevice"):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert r["menu_options"][0] == "account_local"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "account_local"})
        assert r["step_id"] == "account_local"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"username": "u", "password": "p"})
        assert r["type"] is FlowResultType.FORM and r["step_id"] == "saved_device"
        assert r["description_placeholders"]["robot"] == "Robot"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_HOST: "192.0.2.20", "name": "Jonr P20 Pro"})
    assert r["type"] is FlowResultType.CREATE_ENTRY and r["title"] == "Jonr P20 Pro"
    await hass.async_block_till_done()          # the new entry sets itself up
    return r


async def test_guided_setup_creates_local_entry_with_map(hass: HomeAssistant, no_cloud, miot) -> None:
    r = await _guided(hass)
    data = r["data"]
    assert data[CONF_MAP_MODE] == MAP_MODE_SAVED and data[CONF_TOKEN] == "1" * 32
    assert PENDING_MAP_KEY in data
    # nothing of the Xiaomi session is persisted
    assert not {"username", "password", "service_token", "ssecurity", "pass_token", "user_id"} & set(data)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED
    cam = _ids(hass, "camera")[0]
    assert set(hass.states.get(cam).attributes["rooms"]) == {"3", "4"}
    assert PENDING_MAP_KEY not in entry.data            # moved into the Store
    assert not [i for i in ir.async_get(hass).issues if i[1].startswith("saved_map_missing")]


async def test_guided_setup_without_map_raises_repairs_issue(hass: HomeAssistant, no_cloud, miot) -> None:
    r = await _guided(hass, map_ok=False)
    assert PENDING_MAP_KEY not in r["data"]
    assert hass.config_entries.async_entries(DOMAIN)[0].state is ConfigEntryState.LOADED
    issues = [i for i in ir.async_get(hass).issues if i[0] == DOMAIN and i[1].startswith("saved_map_missing")]
    assert issues, "user must be told in Repairs how to get the map"


async def test_guided_setup_wrong_ip_shows_error(hass: HomeAssistant) -> None:
    with _patch_cloud(["ok"]), \
         patch("custom_components.jonr_local.config_flow._probe", side_effect=OSError("timeout")):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "account_local"})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"username": "u", "password": "p"})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_HOST: "192.0.2.99", "name": "X"})
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"base": "cannot_connect_saved"}


async def test_options_map_refresh_with_2fa(hass: HomeAssistant, no_cloud, miot) -> None:
    entry = MockConfigEntry(domain=DOMAIN, version=2, unique_id=ROBOT["mac"], data={
        CONF_HOST: ROBOT["localip"], CONF_TOKEN: ROBOT["token"], CONF_MODEL: MODEL,
        CONF_MAC: ROBOT["mac"], CONF_MAP_MODE: MAP_MODE_SAVED})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert [i for i in ir.async_get(hass).issues if i[1].startswith("saved_map_missing")]
    with _patch_cloud(["2fa", "ok"]), \
         patch("custom_components.jonr_local.config_flow.download_map_once",
               return_value=(synthetic_map(), INFOS)) as dl:
        r = await hass.config_entries.options.async_init(entry.entry_id)
        assert r["type"] is FlowResultType.MENU and r["menu_options"] == ["map_refresh", "settings"]
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "map_refresh"})
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"username": "u", "password": "p"})
        assert r["step_id"] == "map_twofa"
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"code": "123456"})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "map_refreshed"
    assert "Room A (3)" in r["description_placeholders"]["rooms"]
    assert dl.call_args.args[1:3] == ("de", "123")
    await hass.async_block_till_done()
    assert set(hass.states.get(_ids(hass, "camera")[0]).attributes["rooms"]) == {"3", "4"}
    assert not [i for i in ir.async_get(hass).issues if i[1].startswith("saved_map_missing")]


async def test_options_settings_still_reachable(hass: HomeAssistant, no_cloud, miot) -> None:
    entry = await _setup(hass, miot)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "settings"})
    assert r["step_id"] == "settings"
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"error_notifications": False})
    assert r["type"] is FlowResultType.CREATE_ENTRY and r["data"]["error_notifications"] is False


def test_download_map_once_uses_lan_names_and_validates() -> None:
    dev = MagicMock()
    dev.map_obj_name.return_value = "u/d/0"
    dev.last_map_infos_file = "u/d/1"
    cloud = MagicMock()
    cloud.map_url.side_effect = lambda server, did, obj, ep, raw_obj: f"https://x/{obj}"
    cloud.download.side_effect = lambda url: synthetic_map().encode() if url.endswith("/0") else INFOS.encode()
    raw_map, raw_infos = download_map_once(cloud, "de", "123", dev)
    assert json.loads(raw_map)["mapId"] == 3 and "Test floor" in raw_infos
    cloud.download.side_effect = lambda url: None
    with pytest.raises(ValueError, match="no map file"):
        download_map_once(cloud, "de", "123", dev)
    dev.map_obj_name.return_value = None
    with pytest.raises(ValueError, match="no map yet"):
        download_map_once(cloud, "de", "123", dev)


# --- multi-floor: every saved map from the catalogue, switchable locally --------
from custom_components.jonr_local.saved_map import build_views, catalog_map_files  # noqa: E402


def _catalog_entry(map_id, name, status, room_names, room_ids=None):
    f = json.loads(synthetic_map(map_id))["fields"]
    areas = json.loads(f[3])
    for i, a in enumerate(areas):
        a["name"] = room_names[i]
        if room_ids:
            a["room_id"] = room_ids[i]
    return {"mapId": map_id, "name": name, "saved": 1, "status": status, "mapData": f[0],
            "areas": json.dumps(areas), "virtualWalls": "", "mopWalls": "", "carpet": "", "thres": "",
            "carpetprefer": []}


TWO_FLOORS = json.dumps([
    _catalog_entry(3, "Parter", 1, ["Room A", "Room B"]),
    _catalog_entry(5, "Pietro", 0, ["Attic", "Office"], room_ids=[8, 9]),
    {"mapId": 0, "name": "", "saved": 0, "status": 0, "mapData": "x"},   # live draft: never a target
])


def test_catalog_map_files_and_build_views() -> None:
    files = catalog_map_files(TWO_FLOORS)
    assert sorted(files) == [3, 5]
    views, active = build_views(synthetic_map(3).encode(), TWO_FLOORS.encode())
    assert active == 3 and sorted(views) == [3, 5]
    assert views[5].room_names == {8: "Attic", 9: "Office"} and views[5].map_name == "Pietro"
    # catalogue alone (no current-map file) still yields every floor; status=1 is active
    views, active = build_views(None, TWO_FLOORS.encode())
    assert active == 3 and sorted(views) == [3, 5]


async def test_switch_floor_locally(hass: HomeAssistant, no_cloud, miot) -> None:
    entry = await _setup(hass, miot)
    vac = _ids(hass, "vacuum")[0]
    resp = await hass.services.async_call(DOMAIN, "import_map", {
        "entity_id": vac, "map_raw": synthetic_map(3), "map_infos_raw": TWO_FLOORS},
        blocking=True, return_response=True)
    assert resp[vac]["maps"] == {"3": "Parter", "5": "Pietro"}
    await hass.async_block_till_done()
    sel = [s for s in _ids(hass, "select") if s.endswith("active_map")][0]
    st = hass.states.get(sel)
    assert st.state == "Parter" and st.attributes["options"] == ["Parter", "Pietro"]

    miot.call_action_by.reset_mock()
    miot.call_action_by.return_value = {"code": 0}
    await hass.services.async_call("select", "select_option",
                                   {"entity_id": sel, "option": "Pietro"}, blocking=True)
    await hass.async_block_till_done()
    assert (17, 9, [{"did": "-", "piid": 58, "value": 5}]) in [c.args for c in miot.call_action_by.call_args_list]
    assert hass.states.get(sel).state == "Pietro"
    cam = _ids(hass, "camera")[0]
    assert set(hass.states.get(cam).attributes["rooms"]) == {"8", "9"}
    # room services follow the active floor
    with pytest.raises(HomeAssistantError, match="not in the saved map"):
        await hass.services.async_call(DOMAIN, "clean_segment", {"entity_id": vac, "segments": [3]}, blocking=True)

    # a refused switch keeps the previous floor
    miot.call_action_by.return_value = {"code": -9999}
    with pytest.raises(HomeAssistantError, match="did not accept"):
        await hass.services.async_call("select", "select_option",
                                       {"entity_id": sel, "option": "Parter"}, blocking=True)
    assert hass.states.get(sel).state == "Pietro"

    # the active floor survives a restart
    miot.call_action_by.return_value = {"code": 0}
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(sel).state == "Pietro"
    assert set(hass.states.get(cam).attributes["rooms"]) == {"8", "9"}


async def test_legacy_single_map_store_still_loads(hass: HomeAssistant, no_cloud, miot, hass_storage) -> None:
    entry_id = "legacyentry"
    hass_storage[f"{DOMAIN}_saved_map_{entry_id}"] = {"version": 1, "key": f"{DOMAIN}_saved_map_{entry_id}", "data": {
        "map_raw": synthetic_map(3), "map_infos_raw": INFOS, "imported_at": "x", "source": "v0.2",
        "prefer_overrides": {"3": {"wind": 3}}}}
    entry = MockConfigEntry(domain=DOMAIN, version=2, unique_id="aa:bb:cc:dd:ee:09", entry_id=entry_id, data={
        CONF_HOST: "192.0.2.10", CONF_TOKEN: "0" * 32, CONF_MODEL: MODEL,
        CONF_MAC: "aa:bb:cc:dd:ee:09", CONF_MAP_MODE: MAP_MODE_SAVED})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    rooms = hass.states.get(_ids(hass, "camera")[0]).attributes["rooms"]
    assert rooms["3"]["prefer"]["wind"] == 3
