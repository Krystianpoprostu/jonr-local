# MIoT spec: xtl.vacuum.xm2216 (JONR P20 Pro)

Źródło: `urn:miot-spec-v2:device:vacuum:0000A006:xtl-xm2216:4` (miot-spec.org, kopia w `docs/spec/`).
Firmware testowanego robota: `4.5.6_0805`. Kolumna **lokalnie** to wynik `tools/probe_props.py` (2026-11-06, UDP z LAN, internet włączony):
`OK` = code 0, `—` = właściwość nieodczytywalna wg spec, inne = opis błędu. Wartości nie są publikowane (część jest prywatna);
pełny zrzut leży w `local_data/` (poza gitem).

Akcje zweryfikowane lokalnie: **17.12 get-map-data** → out 38 = `"<uid>/<did>/0"`, **17.13 get-map-infos** → out 37 = `"<uid>/<did>/1"`
(oba natychmiast, code 0). To nazwy plików w chmurze KS3, a nie treść mapy.


## siid 1 `device-information`

| piid | nazwa | format | dostęp | lokalnie | zakres / wartości |
|---|---|---|---|---|---|
| 1 | manufacturer | string | read | pusta odpowiedź |  |
| 2 | model | string | read | pusta odpowiedź |  |
| 3 | serial-number | string | read | pusta odpowiedź |  |
| 4 | firmware-revision | string | read | pusta odpowiedź |  |
| 5 | serial-no | string | read,notify | pusta odpowiedź |  |

## siid 2 `vacuum`

| piid | nazwa | format | dostęp | lokalnie | zakres / wartości |
|---|---|---|---|---|---|
| 2 | status | uint8 | read,notify | OK | 1=Idle, 2=Busy, 3=Delay, 4=Mopping, 5=Sweeping and Mopping, 6=Paused, 7=Sweeping, 8=Error, 9=Charging, 10=Go Charging, 11=BreakCharging, 12=GoWash, 13=Charged, 14=BuildingMap, 15=Updating, 16=Sleeping, 17=Relocation, 18=StationWorking, 19=MappingPause, 20=GoChargeBreak, 21=WashBreak, 22=Linking Device, 23=GoDust |

| aiid | akcja | in (piid) | out (piid) |
|---|---|---|---|
| 1 | start-sweep |  |  |
| 2 | stop-sweeping |  |  |
| 7 | pause-sweeping |  |  |

## siid 16 `battery`

| piid | nazwa | format | dostęp | lokalnie | zakres / wartości |
|---|---|---|---|---|---|
| 1 | battery-level | uint8 | read,notify | OK | 0..100 |

| aiid | akcja | in (piid) | out (piid) |
|---|---|---|---|
| 1 | start-charge |  |  |

## siid 17 `robotic-vacuum`

| piid | nazwa | format | dostęp | lokalnie | zakres / wartości |
|---|---|---|---|---|---|
| 1 | disturb-switch | bool | read,notify | OK |  |
| 2 | break-clean-switch | bool | read,notify | OK |  |
| 3 | collect-dust | bool | write-only/param | — |  |
| 4 | dry-mop | bool | write-only/param | — |  |
| 5 | wash-mop | bool | write-only/param | — |  |
| 6 | child-lock | bool | read,notify | OK |  |
| 7 | carpet-boost-switch | bool | read,notify | OK |  |
| 8 | clean-type | uint8 | write-only/param | — | 1=FullClean, 2=QMAP, 3=AreaClean, 4=ZoneClean, 5=CarpetClean, 6=SpotClean |
| 9 | clean-type-status | uint8 | read,notify | OK | 0=None, 1=Idle, 2=Full Clean, 3=Full Pause, 4=Full Resume, 5=QMAP, 6=QMAP Pause, 7=QMAP Resume, 8=Area Clean, 9=Area Pause, 10=Area Resume, 11=Zone Clean, 12=Zone Pause, 13=Zone Resume, 14=Carpet Clean, 15=Carpet Pause, 16=Carpet Resume, 17=Spot Clean, 18=Spot Pause |
| 10 | clean-mode | uint8 | read,notify | OK | 0=BothWork, 1=OnlySweep, 2=OnlyMop, 3=SweepFirst, 4=Custom |
| 11 | carpet-clean-prefer | uint8 | read,notify | OK | 0=Adaptive, 1=Evade, 2=Only, 3=Ignore |
| 12 | water-mode | uint8 | read,notify | OK | 0=Low, 1=Mid, 2=High |
| 13 | fan-mode | uint8 | read,notify | OK | 0=Quiet, 1=Auto, 2=Strong, 3=Max |
| 14 | clean-count | uint8 | read,notify | OK | 1=Once, 2=Twice |
| 15 | volume | uint8 | read,notify | OK | 0..100 |
| 16 | scheduled-timer | string | write-only/param | — |  |
| 17 | scheduled-timers | string | read,notify | OK |  |
| 18 | disturb-time-action | string | write-only/param | — |  |
| 19 | disturb-time | string | read,notify | OK |  |
| 20 | dust-collection-freq | uint8 | read,notify | OK | 0=None, 1=EveryTime, 2=LowFrequency, 3=MediumFrequency, 4=HighFrequency |
| 21 | drying-switch | bool | read,notify | OK |  |
| 22 | drying-time | uint8 | read,notify | OK | 120=TwoHours, 180=ThreeHours, 240=FourHours |
| 23 | mop-wash-frequency | uint8 | read,notify | OK | 5=5 Min, 10=10 Min, 15=15 Min |
| 24 | time-zone | int16 | read,notify | OK | -1000..1000 |
| 25 | language-voice | uint8 | read,notify | OK | 1=China, 2=English, 3=Russian, 4=German, 5=Italian, 6=French, 7=Poland, 8=Spain, 9=Korean, 10=China-TW, 11=Vietnam |
| 26 | clean-time | uint32 | read,notify | OK | 0..999999 |
| 27 | clean-area | uint16 | read,notify | OK | 0..65535 |
| 28 | battery | uint8 | read,notify | OK | 0..100 |
| 29 | clean-area-total | uint16 | read,notify | OK | 0..65535 |
| 30 | clean-count-total | uint16 | read,notify | OK | 0..65535 |
| 31 | clean-time-total | uint32 | read,notify | OK | 0..2094967295 |
| 32 | consumables | string | read,notify | OK |  |
| 33 | consumables-action | string | write-only/param | — |  |
| 34 | clean-values | string | read,notify | OK |  |
| 35 | error | uint16 | read,notify | OK | 0..65535 |
| 36 | message | uint16 | read,notify | OK | 0..65535 |
| 37 | map-infos | string | write-only/param | — |  |
| 38 | map-data | string | write-only/param | — |  |
| 39 | save-map-switch | bool | read,notify | OK |  |
| 40 | areas-split | string | write-only/param | — |  |
| 41 | areas-merge | string | write-only/param | — |  |
| 42 | erp-switch | bool | read,notify | OK |  |
| 43 | mop-augment-switch | bool | read,notify | OK |  |
| 44 | auto-solution-switch | bool | read,notify | OK |  |
| 45 | mop-wash-temp | uint8 | read,notify | OK | 0=Nor, 1=Low, 2=High |
| 46 | clean-records | string | read,notify | brak odpowiedzi |  |
| 47 | multifloor-switch | bool | read,notify | OK |  |
| 48 | return-status | uint8 | read,notify | OK | 0=None, 1=Idle, 2=Run, 3=Pause, 4=Resume |
| 49 | robot-status | string | read,notify | OK |  |
| 50 | auto-water-change | bool | read,notify | OK |  |
| 51 | clean-water-cistern | uint8 | read,notify | OK | 0=Normal, 1=Uninstalled, 2=Unusable, 3=FluidLow |
| 52 | drain-cistern | uint8 | read,notify | OK | 0=Nor, 1=Uninstall, 2=Unusable |
| 53 | dust-bag | uint8 | read,notify | OK | 0=Nor, 1=Uninstall |
| 54 | mop-clean-tank | uint8 | read,notify | OK | 0=Nor, 1=Uninstall |
| 55 | robot-set-status | uint8 | write-only/param | — | 0..255 |
| 56 | virtual-walls-action | string | write-only/param | — |  |
| 57 | save-map-action | string | write-only/param | — |  |
| 58 | map-id | uint8 | write-only/param | — | 0..99 |
| 59 | map-info | string | write-only/param | — |  |
| 60 | area-info | string | write-only/param | — |  |
| 61 | voice-lang-info | string | write-only/param | — |  |
| 62 | control-order | uint8 | write-only/param | — | 0=Stop, 1=Up, 2=Left, 3=Right, 4=Down |
| 63 | push-code | uint16 | write-only/param | — | 0..65535 |
| 64 | expanded-map | bool | read,notify | OK |  |
| 65 | fine-drag | uint8 | read,notify | OK | 0=Fast, 1=Daily, 2=Fine |
| 66 | aw-check-data | string | read,notify | OK |  |
| 67 | aw-check-switch-data | bool | write-only/param | — |  |
| 68 | exit-control-data | bool | write-only/param | — |  |
| 70 | customization-action | string | write-only/param | — |  |
| 71 | carpetmarking-action | string | write-only/param | — |  |
| 72 | aw-check-sign | bool | read,notify | OK |  |
| 74 | carpet-cleantwice | bool | read,notify | OK |  |
| 75 | carpet-cleanchoice | bool | read,notify | OK |  |
| 76 | room-edite-result | string | read,notify | OK |  |
| 77 | cp-preference-data | string | write-only/param | — |  |
| 78 | language-ver | string | read,notify | OK |  |
| 79 | station-error | uint16 | read,notify | OK | 0..65535 |

| aiid | akcja | in (piid) | out (piid) |
|---|---|---|---|
| 1 | start-clean | 8:clean-type, 34:clean-values |  |
| 2 | pause-continue-work | 55:robot-set-status |  |
| 3 | stop-clean |  |  |
| 4 | seek-robot |  |  |
| 5 | set-virtual-walls | 56:virtual-walls-action |  |
| 6 | save-map | 57:save-map-action |  |
| 7 | edite-map | 59:map-info |  |
| 8 | del-map | 58:map-id |  |
| 9 | switch-map | 58:map-id |  |
| 10 | fast-building |  |  |
| 11 | clean-building |  |  |
| 12 | get-map-data |  | 38:map-data |
| 13 | get-map-infos |  | 37:map-infos |
| 14 | report-log |  |  |
| 15 | edite-area-info | 60:area-info |  |
| 16 | set-schedule-timer | 16:scheduled-timer |  |
| 17 | set-split-area | 40:areas-split |  |
| 18 | set-merge-areas | 41:areas-merge |  |
| 19 | sync-time-zone | 24:time-zone |  |
| 20 | reset-consumable | 33:consumables-action |  |
| 21 | switch-voice-lang | 61:voice-lang-info |  |
| 22 | give-up-map-extended |  |  |
| 23 | clear-maps-except | 58:map-id |  |
| 24 | set-disturb-switch | 1:disturb-switch |  |
| 25 | set-break-switch | 2:break-clean-switch |  |
| 26 | set-fan-mode | 13:fan-mode |  |
| 27 | set-water-mode | 12:water-mode |  |
| 28 | set-clean-count | 14:clean-count |  |
| 29 | set-save-map-switch | 39:save-map-switch |  |
| 30 | set-disturb-time | 18:disturb-time-action |  |
| 31 | set-volume | 15:volume |  |
| 32 | set-dust-collection | 20:dust-collection-freq |  |
| 33 | set-carpet-prefer | 11:carpet-clean-prefer |  |
| 34 | set-carpet-boost | 7:carpet-boost-switch |  |
| 35 | set-mop-augment | 43:mop-augment-switch |  |
| 36 | set-child-lock | 6:child-lock |  |
| 38 | set-erp-switch | 42:erp-switch |  |
| 39 | set-auto-solution | 44:auto-solution-switch |  |
| 40 | set-wash-mop | 5:wash-mop |  |
| 41 | set-dry-mop | 4:dry-mop |  |
| 42 | set-collect-dust | 3:collect-dust |  |
| 43 | set-drying-time | 22:drying-time |  |
| 44 | set-mop-wash-freq | 23:mop-wash-frequency |  |
| 45 | set-mop-wash-temp | 45:mop-wash-temp |  |
| 46 | set-clean-mode | 10:clean-mode |  |
| 47 | set-mfloor-switch | 47:multifloor-switch |  |
| 48 | set-drying-switch | 21:drying-switch |  |
| 49 | manual-control | 62:control-order |  |
| 50 | fine-drag-switch | 65:fine-drag |  |
| 51 | awater-check-switch | 67:aw-check-switch-data |  |
| 52 | exit-control-switch | 68:exit-control-data |  |
| 53 | customization-rooms | 70:customization-action |  |
| 54 | carpet-marking | 71:carpetmarking-action |  |
| 55 | setcarpetcleantwice | 74:carpet-cleantwice |  |
| 56 | setcarpetcleanfirst | 75:carpet-cleanchoice |  |
| 57 | carpet-preference | 77:cp-preference-data |  |

| eiid | zdarzenie | argumenty |
|---|---|---|
| 1 | map-data-report | 38:map-data |
| 2 | map-infos-report | 37:map-infos |
| 3 | message-notification | 63:push-code |

## siid 7 `bit-test`

| piid | nazwa | format | dostęp | lokalnie | zakres / wartości |
|---|---|---|---|---|---|
| 1 | functional-testing | uint8 | write-only/param | — | 1=Wheel, 2=Side-Brush, 3=Water-Pumb, 4=Roll-Brush, 5=Fan, 6=Cloth-Motor, 7=Bottom-View, 8=Imu, 9=Dust-Box, 10=Rag-Hall, 11=Collision-Board, 12=Forward-Sensor, 13=Side-Sensor, 14=Ultrasonic-Sensor, 15=Charge, 16=All, 17=Radar-Calibration, 18=Ins-Calibration, 19=Line-Calibration, 22=Sideline-Calibration, 23=Ai-Calibration, 24=Lds-test |
| 2 | common-params | uint8 | write-only/param | — | 1=Wheel-success, 2=Wheel-fail, 3=Side-brush-success, 4=Side-brush-fail, 5=Water-pumb-success, 6=Water-pumb-fail, 7=Roll-brush-success, 8=Roll-brush-fail, 9=Fan-success, 10=Fan-fail, 11=Cloth-motor-success, 12=Cloth-motor-fail, 13=Bottom-view-success, 14=Bottom-view-fail, 15=Imu-success, 16=Imu-fail, 17=Dust-box-success, 18=Dust-box-fail, 19=Rag-hall-success, 20=Rag-hall-fail, 21=Collision-board-success, 22=Collision-board-fail, 23=Forward-snsor-success, 24=Forward-sensor-fail, 25=Side-sensor-success, 26=Side-sensor-fail, 27=Ultra-sensor-success, 28=Ultra-sensor-fail, 29=Charge-success, 30=Charge-fail, 31=Radar-Calibration-success, 32=Radar-Calibration-fail, 33=Ins-Calibration-success, 34=Ins-Calibration-fail, 35=Line-Calibration-success, 36=Line-Calibration-fail, 37=Sideline-Calibration-success, 38=Sideline-Calibration-fail, 39=Ai-calibration-success, 40=Ai-calibration-fail, 41=Lds-test-success, 42=Lds-test-fail |

| aiid | akcja | in (piid) | out (piid) |
|---|---|---|---|
| 1 | bit-test | 1:functional-testing |  |
| 2 | enter-bit-mode |  |  |
| 3 | quit-bit-mode |  |  |

| eiid | zdarzenie | argumenty |
|---|---|---|
| 1 | bit-test-result | 2:common-params |

## Czego lokalnie nie ma / nie działa (test 2026-11-06)

| Co | Wynik | Dowód |
|---|---|---|
| Treść mapy, lista pokoi, pozycja robota | **brak lokalnie**: spec nie ma właściwości pozycji ani pokoi; 17.12/17.13 dają tylko nazwy plików KS3 | probe 17.12/17.13; pozycja jest tylko w polu f2 pliku mapy (`xtl_map.py`) |
| Starsze komendy miIO (`get_room_mapping`, `get_map_v1`, `get_fresh_map`, `get_persist_map`, `get_multi_maps_list`, `get_timer`, `get_status` …) | robot nie odpowiada (ignoruje) | probe; dla porównania `get_properties` z pustą listą odpowiada |
| Usługi TCP na robocie (21, 22, 23, 53, 80, 443, 554, 1883, 4433, 5000, 6668, 8000, 8053, 8080, 8443, 8883, 9999, 10000, 54321) | wszystkie zamknięte | probe connect() |
| 17.46 clean-records | brak odpowiedzi także przy pojedynczym odczycie | 2 próby, timeout 8 s |
| siid 1 (device-information) | pusta lista w odpowiedzi | model i FW są dostępne przez `miIO.info` |
| 17.17 scheduled-timers | odpowiada, wartość `[]`: **robot nie ma zapisanych harmonogramów** | probe (dwukrotnie) |

## Testy komend z ruchem i zapisem (2026-11-06, za zgodą użytkownika, internet włączony)

Skrypt: `tools/motion_test.py`. In-params wysyłane w formie `{"did":"-","piid":N,"value":V}`, tak jak w integracji.

| Test | Komenda | Wynik | Odczyt potwierdzający |
|---|---|---|---|
| A: pokój | 17.3, po 2 s 17.1 `[8:3, 34:"[6]"]` | ✅ code 0, robot wyjechał | 17.9 = 8 *Area Clean*, 17.34 = `[6]`, 2.2 = 7 *Sweeping* |
| B: strefa | 17.3, po 2 s 17.1 `[8:4, 34:"[402,373,422,373,422,393,402,393]"]` | ✅ code 0, robot wyjechał | 17.9 = 11 *Zone Clean*, 17.34 = te same 8 liczb |
| stop + dok | 17.3, potem 16.1 | ✅ code 0 | 2.2: 1 → 10 *Go Charging* → 17 *Relocation* → 9/13 |
| C1: nazwa pokoju (ta sama) | 17.15 `[60:{"mapId":1,"rooms":[{"roomId":6,"name":"Korytarz","category":9}]}]` | ❌ **-9999 user ack timeout** (2 próby: w ruchu i w stacji) | po komendzie 2.2 = 1 *Idle*, 17.9 = -1. Za pierwszym razem robot **przerwał powrót do stacji** i trzeba było ponowić 16.1; w stacji wrócił sam do *Charging* |
| C2: ustawienia pokoju (te same) | 17.53 `[70:{"total":1,"index":0,"customdata":{"type":1,"data":[{"I":1,"R":6,"K":0,"F":1,"W":1,"C":1,"D":1}]}}]` | ✅ code 0 | wartości identyczne z obecnymi, więc samego efektu nie widać. Do potwierdzenia zmianą wartości i odczytem `prefer` z mapy |

Wnioski:
- Sprzątanie pokoi i stref działa **lokalnie** z ID i współrzędnymi z mapy. 17.34 + 17.9 pokazują w czasie pracy, co robot sprząta (podstawa diagnostyki w Etapie 5).
- 17.15 (zmiana nazwy/typu pokoju) **lokalnie nie działa** na FW 4.5.6_0805 i zakłóca bieżące zadanie. W trybie lokalnym usługa `set_room_info` powinna być wyłączona albo dostępna tylko przez chmurę.
- 17.53 jest przyjmowane lokalnie (code 0).

Nie testowane: 17.9 switch-map (jedna mapa, brak celu), 17.16 set-schedule-timer, 17.30 (DND), wszystko przy odciętym internecie (Etap 3).
Spec ma też **17.16 set-schedule-timer** (zapis harmonogramu w robocie), którego integracja nie używa.
