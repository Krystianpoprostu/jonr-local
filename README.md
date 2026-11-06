# JONR Local

Home Assistant integration for the **JONR P20 Pro** robot vacuum (MIoT model
`xtl.vacuum.xm2216`) that runs **entirely over your LAN**. The robot can be
blocked from the internet on your router and everything keeps working:
cleaning, rooms, zones, the dock, consumables, errors, settings, and the
floor-plan map.

The map is the one thing the robot does not hand over the LAN. You download
it **once** from the Mi cloud with a small tool, import it into Home
Assistant, and from then on it is served locally.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Krystianpoprostu&repository=jonr-local&category=integration)

> Unofficial. Not affiliated with JONR or Xiaomi. Use at your own risk.

## Features

| | |
|---|---|
| 🧹 Cleaning | start / pause / stop / dock / locate, **room cleaning** by room id, **zone cleaning**, ×1/×2 passes, manual drive |
| ⚙️ Modes | work mode, fan, water, mop route, passes, carpet strategy, carpet boost, edge mopping, resume after charge |
| 🏠 Dock | wash / dry mops, empty dust, auto-dry, auto-empty, drying time, mop-wash interval, tank and bag states |
| 🧰 Consumables | life of 7 parts + reset buttons |
| 🗺️ Map | floor-plan camera and an interactive Lovelace card (tap rooms to clean), served from the saved copy; **multiple floors** with an *Active map* switch |
| 📋 Last-clean log | sensor + `jonr_local_clean_finished` event: rooms targeted, m² cleaned vs. room area (coverage %), dock returns, errors |
| 🚨 Errors | robot and dock error sensors, bus events, optional notifications with the fix-it text |
| 🌙 Settings | Do-Not-Disturb window and exceptions, child lock, volume, voice language, statistics |

What is local and what is not, with the evidence (protocol probes and an
offline test with the robot cut off from the internet):
**[docs/LOCAL_MODE.md](docs/LOCAL_MODE.md)**.

Not available offline: the live robot position on the map, renaming rooms
from HA (the robot rejects it over the LAN, so do it in Mi Home), and fetching
a **new** map after you re-map your home (needs the robot online for a moment).

## Requirements

- Home Assistant 2024.12 or newer, on the same LAN as the robot.
- The robot paired in the Mi Home app (only needed once, for its token and map).

## Installation

**HACS:** HACS → ⋮ → *Custom repositories* → `https://github.com/Krystianpoprostu/jonr-local`,
category *Integration* → install **JONR Local** → restart Home Assistant.

**Manual:** copy `custom_components/jonr_local/` into your HA `config/custom_components/`
and restart.

> If you used `jonr-vac` / *JONR Vacuum* before: remove that integration's
> entries first (both use the robot's MAC as their unique id).

## Setup (everything in the Home Assistant UI)

1. *Settings → Devices & services → Add integration → **JONR Local***.
2. Choose **Xiaomi account once → fully local** and sign in with the account
   the robot is paired to in Mi Home (captcha and e-mail codes are asked for
   when Xiaomi wants them).
3. Confirm the robot's IP address and give it a name (entity ids are built
   from the name). The map is downloaded once.
4. Done. The password and the Xiaomi session are **not stored**; the
   integration now talks only to the robot on your LAN. You can block the
   robot's internet access on your router.

**Several floors:** map each floor in Mi Home first (enable multi-floor maps there, robot online), then download the map — all saved floors come in at once. Switch floors with the *Active map* entity after carrying the robot to that floor.

**Later, after re-mapping your home or changing rooms in Mi Home:** let the
robot online until Mi Home shows the new map, then *JONR Local → Configure →
Download / refresh the map from your Xiaomi account*.

If the map is missing (e.g. the download failed during setup), Home Assistant
shows a **Repairs** entry with these steps.

Add the map card to a dashboard:

```yaml
type: custom:xiaomi-vac-card
vacuum: vacuum.<your_robot>
map: camera.<your_robot>_map
water: select.<your_robot>_water_level   # use your entity ids
fan: select.<your_robot>_fan_speed
```

Clean rooms from an automation (room ids are shown after the map download and
in the map camera's `rooms` attribute):

```yaml
actions:
  - action: jonr_local.clean_segment
    target:
      entity_id: vacuum.<your_robot>
    data:
      segments: [3, 4, 5]
```

### Advanced: without signing in from Home Assistant

Prefer not to enter your Xiaomi password in HA? Use the PC tools instead:
`tools/get_token.py` (QR login, token to `.env`), add the integration with
**Device IP & token + saved map**, then `tools/dump_map.py` + `tools/push_map.py`.
See [docs/LOCAL_MODE.md](docs/LOCAL_MODE.md).

## Documentation

| Doc | Content |
|---|---|
| [Fully local mode](docs/LOCAL_MODE.md) | What is local, map dump and import, last-clean log, limits, tools |
| [Services](docs/SERVICES.md) | All actions with fields and examples |
| [Entities](docs/ENTITIES.md) | Every entity, per platform |
| [Events](docs/EVENTS.md) | Error events and recipes |
| [Notifications](docs/NOTIFICATIONS.md) | Error notifications |
| [Map card](docs/MAP_CARD.md) | The bundled card and the vector endpoint |
| [Translations](docs/TRANSLATIONS.md) | UI languages |
| [Research log](docs/FINDINGS.md) | (Polish) How every local/cloud claim was verified: [code audit](docs/LOCAL_VS_CLOUD.md), [MIoT probe](docs/MIOT_SPEC.md), [offline test](docs/OFFLINE_TEST.md) |

The upstream cloud setup paths (*Email & password* with the live cloud map and
MQTT; plain *Device IP & token* without a map) are still available. See
[docs/INSTALLATION.md](docs/INSTALLATION.md).

## Development

```bash
pip install pytest-homeassistant-custom-component python-miio
pytest tests            # harness tests run with network sockets disabled
```

## Credits & license

MIT, see [LICENSE](LICENSE) and [CREDITS.md](CREDITS.md). Built on
[moriceh/jonr-vac](https://github.com/moriceh/jonr-vac) and
[letitbe-dull/xiaomi-vac](https://github.com/letitbe-dull/xiaomi-vac) (MIT;
upstream notice in [LICENSE.xiaomi-vac](LICENSE.xiaomi-vac)). Tools use
[PiotrMachowski/Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor)
(MIT, not vendored) and [python-miio](https://github.com/rytilahti/python-miio)
(GPL-3.0, dependency only).
