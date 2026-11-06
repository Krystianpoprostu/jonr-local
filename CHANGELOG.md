# Changelog

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
