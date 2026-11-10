[← Back to the README](../README.md)

# Fully local mode ("Device IP & token + saved map")

This fork adds a third setup path. Home Assistant talks to the robot **only over
the LAN**. The floor plan comes from a copy of the robot's map that you download
**once** from the Mi cloud and import into HA. The robot can stay cut off from
the internet permanently.

Evidence for every claim below is in [FINDINGS.md](FINDINGS.md),
[LOCAL_VS_CLOUD.md](LOCAL_VS_CLOUD.md), [MIOT_SPEC.md](MIOT_SPEC.md) and
[OFFLINE_TEST.md](OFFLINE_TEST.md). All of it was tested on a JONR P20 Pro with
firmware `4.5.6_0805`.

## What works locally, what needs the cloud

| Feature | Fully local mode |
|---|---|
| Start / pause / stop / return to dock, locate | ✅ LAN |
| Fan, water, work mode, passes, mop route, volume, all settings switches and selects | ✅ LAN |
| Room cleaning (`jonr_local.clean_segment`) with room ids from the saved map | ✅ LAN (ids not in the saved map are refused) |
| Zone cleaning (`jonr_local.clean_zone`) | ✅ LAN |
| Per-room settings and cleaning order (`set_room_clean_mode`, `reset_room_clean_modes`, `set_clean_sequence`) | ✅ LAN (17.53). Changes are also written into the saved copy |
| Dock: wash / dry / empty, consumables and their reset, errors and notifications, DND window | ✅ LAN |
| Map camera, vector card endpoint, room names | ✅ from the saved copy (static: no live robot position) |
| Last-clean log (sensor + `jonr_local_clean_finished` event) | ✅ LAN telemetry (new in this fork) |
| Rename / re-type a room (`set_room_info`) | ❌ blocked. Over the LAN 17.15 answers `-9999` and knocks the robot out of its task. Rename in Mi Home, then refresh the saved map |
| Live robot position and trace on the map | ❌ only in the cloud map file |
| Getting a new map after changes in the home | ☁️ one-time sign-in from *Configure* (or the PC tools), then local again |
| MQTT instant updates | ❌ not used. The 10 s LAN poll is the only source |
| Cleaning history from the robot (17.46) | ❌ never answers over the LAN. Use the last-clean log instead |
| Map switching (several floors) | ✅ LAN (17.9) via the *Active map* select; all floors come from one download |

At runtime a local entry creates **no** Xiaomi cloud session, no MQTT client
and no map polling (`__init__.py` → `SavedMapCoordinator`). The harness tests run
with network sockets disabled and fail if any cloud class is even constructed.

## Setup

**In the Home Assistant UI (recommended).** *Add integration → JONR Local →
"Xiaomi account once → fully local"*. Sign in (captcha / e-mail code when
Xiaomi asks), confirm the robot's IP and a name; the token is found and the map
downloaded once. The password and the Xiaomi session are not stored; the
entry carries only IP, token, model, MAC and the map mode. If the map download
fails, a Repairs entry explains how to get it later.

If the robot's IP address changes later, use *JONR Local → ⋮ → Reconfigure*:
the new address is probed with the stored token and must answer with the
same MAC before it is saved; nothing else in the entry changes.

**Without signing in from HA (advanced).**

1. `tools/get_token.py` (QR login with the Mi Home app; the token goes to
   `.env`, mode 600, and is never printed).
2. *Add integration → JONR Local → "Device IP & token + saved map"*: IP,
   token and a name.
3. Download and import the map with the PC tools (next section), or use
   *Configure → Download / refresh the map from your Xiaomi account*.

> Only one entry per robot: all setup paths use the MAC as unique id. Remove an
> existing cloud entry first if you are migrating.

## Map: one-shot download and import

The robot cannot hand its map over the LAN. It only *names* the cloud file
(17.12 / 17.13). The file itself was uploaded the last time the robot was online,
so **the robot does not need internet for the download**. Only the PC running
the tool does.

```bash
python tools/dump_map.py                       # QR login, downloads map + catalogue once
python tools/render_map.py                     # optional: re-render offline, check map.png
python tools/push_map.py vacuum.jonr_p20_pro   # import into HA (jonr_local.import_map)
```

`dump_map.py` writes `local_data/map_dumps/<timestamp>/` (git-ignored):
`map_raw.json`, `map_infos_raw.json`, `rooms.json` (room_id → name, type,
bbox, preferences), `calibration.json`, `attributes.json`, `vector.json`,
`meta.json`, `map.png`. The cloud session lives only in memory.

`push_map.py` calls the `jonr_local.import_map` service with your HA token from
`.env`. The service returns the map id, the room table and the room areas.

## Refreshing the map after changes in the home

1. Temporarily allow the robot to reach the internet (router rule).
2. In Mi Home: re-map, split / merge or rename rooms, and open the map once so
   the robot uploads it.
3. *JONR Local → Configure → Download / refresh the map from your Xiaomi
   account* (or `dump_map.py` + `push_map.py`), then block the robot again.

If the robot ever reports a room id the saved copy does not know, HA raises a
**Repairs** issue "Saved map looks outdated".

## Multiple floors

1. In Mi Home (robot online): turn on multi-floor maps, carry the robot to the
   other floor, map it and save the map. Repeat per floor.
2. *JONR Local → Configure → Download / refresh the map from your Xiaomi
   account*. The robot uploads one map catalogue that holds **every** saved
   floor (raster, rooms, walls, carpets), so all floors arrive in one download.
3. Carry the robot to a floor and pick it in **Active map**
   (`select.<name>_active_map`). The switch is sent over the LAN (switch-map
   17.9). A running task is stopped first, and HA only shows the new floor
   (map, room ids, room services, last-clean log) after the robot accepts it.

The robot reports no "current floor" over the LAN, so HA remembers the last
switch it made. If you switch floors in Mi Home instead, pick the same floor
in HA too.

## Last-clean log

`sensor.<name>_ostatnie_sprzatanie` / `last_clean`: state = coverage % (the area
the robot reports for the task ÷ the saved-map area of the targeted rooms; whole
home = all rooms). Attributes: `kind`, `rooms`, `room_ids`, `area_m2`,
`expected_area_m2`, `dock_returns`, `errors`, `battery_min`, `ended_on_dock`,
`robot_clean_time_s`, start and end times. The last 30 records are kept in HA
storage. Each finished task also fires `jonr_local_clean_finished` with the same
payload.

A task counts as finished when 17.9 returns to Idle, when it sits **paused on the
dock for 10 minutes** (a plain *return to dock* leaves the task open and
resumable), or when a different task replaces it. Mid-clean mop washes (~2 min
on the dock) do not split a session.

The robot reports no per-room completion over the LAN, so coverage is the
closest local answer to "which rooms were skipped". 17.27 counts whole m², so
very short runs show 0.

## Example: daily clean with an explicit room list

```yaml
alias: Sprzątanie robot
triggers:
  - trigger: time
    at: "02:00:00"
actions:
  - action: jonr_local.clean_segment
    target:
      entity_id: vacuum.jonr_p20_pro
    data:
      segments: [3, 4, 5, 6, 7]
mode: single
```

Optional notification when a clean looks incomplete:

```yaml
alias: Robot – niepełne sprzątanie
triggers:
  - trigger: event
    event_type: jonr_local_clean_finished
conditions:
  - condition: template
    value_template: >-
      {{ trigger.event.data.coverage_pct is not none
         and trigger.event.data.coverage_pct < 80 }}
actions:
  - action: persistent_notification.create
    data:
      title: Robot posprzątał tylko część domu
      message: >-
        {{ trigger.event.data.rooms | join(', ') }}:
        {{ trigger.event.data.area_m2 }} z {{ trigger.event.data.expected_area_m2 }} m²
        ({{ trigger.event.data.coverage_pct }} %), powroty do stacji:
        {{ trigger.event.data.dock_returns }}, błędy: {{ trigger.event.data.errors }}
mode: queued
```

## Tools (`tools/`)

| Tool | Network | Purpose |
|---|---|---|
| `get_token.py` | Mi cloud (once) | Token, IP, did and region into `.env`; wraps PiotrMachowski's extractor (expected in `../third_party/`) |
| `envfile.py` | none | Store a secret in `.env` with hidden input |
| `miio_probe.py`, `probe_props.py` | LAN | Read-only MIoT probes |
| `motion_test.py`, `offline_test.py` | LAN | Supervised command tests (the robot moves) |
| `dump_map.py` | robot via LAN + Mi cloud (once) | Map download |
| `render_map.py` | none | Offline render of a dump |
| `push_map.py` | HA REST | Import a dump into HA |
