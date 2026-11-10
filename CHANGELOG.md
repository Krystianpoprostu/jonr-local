# Changelog

## 0.3.4 — 2026-11-10

Change the robot's IP address from Home Assistant.

- *Settings → Devices & services → JONR Local → ⋮ → Reconfigure* asks for
  the new address. It is probed with the stored token and must answer with
  the same MAC before it is saved, so a typo or another device can't take
  over the entry. Only the address changes; map, settings and entity ids
  stay, and the integration reloads.
- Texts in all 15 languages.

## 0.3.3 — 2026-11-07

Map card: rooms only on the floor the robot is on.

- On the page of a floor the robot is not on, rooms are dimmed and can't be
  selected (a short note says to switch the floor first). Room ids repeat
  across floors, so a pick there would have cleaned the same-numbered rooms
  on the active floor.
- The card sends the floor with the rooms (`clean_segment` gets an optional
  `map_id`); the integration refuses a floor that is not the active one —
  also covers a stale card after someone switched floors. Calls without
  `map_id` (automations) behave as before.

## 0.3.2 — 2026-11-07

Room switches — rooms by voice in any language.

- One switch per map room ("Clean Kitchen"): ON cleans that room, OFF
  stops and docks; it reads ON while the robot cleans that room. Voice
  assistants handle on/off switches in every language ("Hey Google, turn on
  kitchen cleaning"), unlike vacuum zones — Google Assistant in Polish sent a
  bare start for "vacuum the kitchen" (whole home).
- Rooms switched on within 3 s are merged into one clean ("turn on kitchen
  and living-room cleaning"); a room switched on during a room clean joins
  it.
- Rooms on another floor are refused. The switch set follows the map: the
  entry reloads itself when a map download adds or removes rooms.

## 0.3.1 — 2026-11-07

Rooms by voice ("Hey Google, vacuum the kitchen").

- The vacuum now supports Home Assistant's native **clean area** (HA 2026.3+):
  it reports the rooms of every saved floor as segments, so you can map HA
  areas to rooms in the vacuum entity's settings. `vacuum.clean_area`, Assist
  ("clean the kitchen") and Google Assistant room commands then clean just
  those rooms. Before this, Google only knew start/stop and a room command
  started a whole-home clean.
- Rooms on a floor the robot is not on are refused (switch the Active map
  first) instead of cleaning the wrong rooms.
- When the saved rooms change after a re-map, HA raises its standard
  "segments changed" repair so the area mapping can be fixed.
- Older HA versions without clean area are unaffected.

## 0.3.0 — 2026-11-07

Multiple floors.

- Every saved map is imported at once: the map catalogue the robot uploads
  carries each floor's raster, rooms, virtual walls, mop walls, carpets and
  sills, so one download yields all floors (verified identical to the
  current-map file: rooms, walls, calibration, dock).
- New **Active map** select on local entries: switches floors with
  switch-map (17.9) over the LAN — a running task is stopped first, and the
  new floor (camera, map card, room ids, room services, last-clean log) is only
  served once the robot acks the switch; a refused switch keeps the old floor.
- The active floor is remembered across restarts; per-room preference
  overrides are kept per floor (older single-map copies migrate automatically).
- *Download / refresh the map* now lists all saved floors.

## 0.2.1 — 2026-11-07

- Fix hassfest validation: the guide link in the *Device IP & token + saved map*
  step is now a description placeholder instead of a URL inside the string.

## 0.2.0 — 2026-11-07

Guided setup inside Home Assistant — no terminal needed.

- New first option in *Add integration*: **Xiaomi account once → fully local**.
  Sign in (password, captcha and e-mail 2FA supported), the robot's IP and
  token are found automatically, you confirm the IP and a name, and the map
  is downloaded once. The password and the Xiaomi session are never stored;
  the entry runs fully local afterwards.
- **Configure → Download / refresh the map from your Xiaomi account** on a
  local entry: one-time sign-in that re-downloads the map (after re-mapping or
  room changes in Mi Home) and shows the rooms it found.
- A **Repairs** issue tells the user, step by step, how to get the map while a
  local entry has none; it disappears once the map is imported.
- Clear errors in the flow (robot not reachable at that IP, robot not on this
  account, no map uploaded yet).
- The Python tools stay available for advanced users.

## 0.1.0 — 2026-11-07

First release of **JONR Local** (`jonr_local`), a separate integration built on
[moriceh/jonr-vac](https://github.com/moriceh/jonr-vac) `e913dbb`.

- New setup path **Device IP & token + saved map**: fully local at runtime (no
  Xiaomi cloud session, no MQTT, no cloud polling); the map is a copy imported
  with the new `jonr_local.import_map` service.
- Tools: `get_token.py` (token without printing it), `dump_map.py` (one-shot map
  download, robot may stay offline), `render_map.py` (offline render),
  `push_map.py` (import into HA), MIoT probes and an offline test runner.
- Last-clean log: sensor + `jonr_local_clean_finished` event with targeted
  rooms, cleaned vs. expected area (coverage), dock returns and errors; Repairs
  issue when the robot reports a room the saved map does not know.
- Saved-map guards: unknown room ids refused, room rename (17.15, broken over
  the LAN on firmware 4.5.6) blocked, per-room preference writes mirrored into
  the saved copy, no map switch control.
- Fix: room personalisation services (`set_room_clean_mode`,
  `reset_room_clean_modes`, `set_room_info`) crashed on the dict-shaped `rooms`
  attribute (also affected cloud entries upstream).
- Separate domain, services (`jonr_local.*`), events and card assets
  (`/jonr-local-card`), so it never collides with the upstream package.
- Tested on firmware `4.5.6_0805` with the robot blocked from the internet;
  evidence in `docs/FINDINGS.md` (Polish) and the linked reports.
