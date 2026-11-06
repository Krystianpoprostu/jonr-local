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
| 🗺️ Map | floor-plan camera and an interactive Lovelace card (tap rooms to clean), served from the saved copy |
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
- The robot paired in the Mi Home app (once, to get its token and its map).
- A PC with Python 3.11+ for the two one-time tools (token, map).

## Installation

**HACS:** HACS → ⋮ → *Custom repositories* → `https://github.com/Krystianpoprostu/jonr-local`,
category *Integration* → install **JONR Local** → restart Home Assistant.

**Manual:** copy `custom_components/jonr_local/` into your HA `config/custom_components/`
and restart.

> If you used `jonr-vac` / *JONR Vacuum* before: remove that integration's
> entries first (both use the robot's MAC as their unique id).

## Setup

```bash
git clone https://github.com/Krystianpoprostu/jonr-local && cd jonr-local
python3 -m venv .venv && . .venv/bin/activate
pip install -r tools/requirements.txt
git clone https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor ../third_party/Xiaomi-cloud-tokens-extractor
```

1. **Token:** `python tools/get_token.py`. Log in with a QR code scanned in
   Mi Home. The robot's IP and token go to `.env` (mode 600) and are never
   printed.
2. **Add the integration:** *Settings → Devices & services → Add integration →
   JONR Local → "Device IP & token + saved map"*. Enter the IP, the token and
   a name. The name becomes the device name, and entity ids are derived from it.
3. **Map:** `python tools/dump_map.py` (one QR login, downloads the map once),
   then put your HA URL and a long-lived access token into `.env`:
   ```bash
   python tools/envfile.py set HA_URL --visible   # e.g. http://192.168.1.20:8123
   python tools/envfile.py set HA_TOKEN           # hidden input
   python tools/push_map.py vacuum.<your_robot>
   ```
4. **Optional:** block the robot's internet access on your router.

Add the map card to a dashboard:

```yaml
type: custom:xiaomi-vac-card
vacuum: vacuum.<your_robot>
map: camera.<your_robot>_map
water: select.<your_robot>_water_level   # use your entity ids
fan: select.<your_robot>_fan_speed
```

Clean rooms from an automation (room ids are in the map camera's `rooms`
attribute and in `local_data/map_dumps/latest/rooms.json`):

```yaml
actions:
  - action: jonr_local.clean_segment
    target:
      entity_id: vacuum.<your_robot>
    data:
      segments: [3, 4, 5]
```

**After re-mapping your home:** let the robot online, adjust the map in
Mi Home, run `dump_map.py` + `push_map.py` again, block the robot again.

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
