# Credits & provenance

This integration is an xtl-only fork of existing MIT/BSD-licensed work. Every
non-trivial idea here traces to one of the sources below.

## letitbe-dull/xiaomi-vac — the base (MIT)

<https://github.com/letitbe-dull/xiaomi-vac>

The whole skeleton comes from this project: the config flow (email/OAuth/
captcha/2FA), the Mi cloud login + map-blob download (`cloud/`), the polling
coordinators, all entity platforms, the map cache, the HTTP map endpoint and
the Lovelace card integration. This fork keeps the cloud path, prunes every
non-xtl brand profile, and adds the xtl (JONR) profile layer on top of that
base. The upstream license text is preserved verbatim in `LICENSE.xiaomi-vac`;
the `Domain: xiaomi_vac` → `jonr_local` rename, the profile pruning
(dreame/viomi/roidmi/ijai/xiaomi) and the xtl-specific code are this fork's
changes.

## Tasshack/dreame-vacuum — map rendering reference

<https://github.com/Tasshack/dreame-vacuum>

Studied for how a MIoT vacuum map reaches a Lovelace card (image entity +
attribute-driven overlays + room-name labels). The xtl renderer
(`spec/profiles/xtl.py`, `xtl_map` path) was built against that display model;
no code was copied.

## Official Jonr/JONR plugin bundle — voice-pack table & UI labels

The built-in voice-pack md5/URL table surfaced by the `install_voice_pack`
service (documented in the repo docs and reflected in `services.yaml`) was
read off the official Mi Home plugin bundle, whose
download endpoints live on Jonr's KS3 bucket (`xtl-data-sg.ks3-sgp.ksyuncs.com/
Jonr/xm2216/sounds/v2/*.tar.gz`). Pack format (plain tar, `audio.conf`,
`Ver`) is the firmware's own.

The same bundle's `keywordN` multilingual tables (11 languages) are the
source for the vendor wording used in `translations/` for
de/es/fr/it/ko/pl/ru/vi/zh-Hans/zh-Hant — the error labels, dock-activity
names and room/map vocabulary the Mi Home app itself shows. Strings the
plugin never had (Home Assistant config flows, service descriptions) are
translated from the English source.

## python-miio — runtime dependency

<https://github.com/rytilahti/python-miio> (and its `miio.MiotDevice`) is a pip
requirement, imported, never copied or vendored. It is GPL-3.0; this project's
MIT license applies to this repository's own code only.

## Pillow, pycryptodome, paho-mqtt — pip requirements

All imported as dependencies, never vendored. See each project's license for
their terms.

## This fork: fully local mode

Fork changes (MIT, like the rest of this repository): the *saved map* setup path
(`saved_map.py`), the last-clean log (`clean_log.py`), the `import_map` service,
the guards for local-only entries, the fix in `vacuum._xtl_map_context` (rooms
dict) and the `tools/`, `docs/` and `tests/` files that come with them. The
evidence behind every local-vs-cloud claim is in `docs/FINDINGS.md`.

## PiotrMachowski/Xiaomi-cloud-tokens-extractor — token / QR login (MIT)

<https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor>

`tools/get_token.py` and `tools/dump_map.py` load `token_extractor.py` at
runtime from a separate clone in `../third_party/` (its QR login was the one
that completed against this account). Nothing from it is vendored here; the
wrappers only add "never print the token" handling on top.

## MIoT spec — `docs/spec/xtl.vacuum.xm2216.v4.json`

A copy of the public device spec served by <https://miot-spec.org>
(`urn:miot-spec-v2:device:vacuum:0000A006:xtl-xm2216:4`), kept so the probe
tools and the docs tables can run offline. The spec belongs to its publisher.

## python-miio in the tools

The tools import python-miio (GPL-3.0) as an installed dependency, the same way
the integration does. Nothing is copied or vendored.
