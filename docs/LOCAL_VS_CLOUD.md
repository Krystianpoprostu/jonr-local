# Lokalnie czy chmura: audyt kodu jonr-vac (Etap 1)

Stan kodu: `moriceh/jonr-vac` @ `e913dbb`. Ścieżki względem `custom_components/jonr_vac/`.
Ten dokument opisuje **to, co wynika z kodu**. Czy dana komenda faktycznie działa lokalnie na naszym firmware
(4.5.6_0805) i bez internetu, sprawdzą Etap 2 (sonda) i Etap 3 (test odcięcia).

## Legenda

| Znacznik | Znaczenie |
|---|---|
| **LOKALNIE** | UDP 54321 do robota przez `miio.MiotDevice` (`device.py`, `XtlVacuumDevice._action/_set/_batch_get`) |
| **CHMURA-API** | HTTPS do `{region}.api.io.mi.com/app/...` przez `cloud/connector.py:XiaomiCloud._call` |
| **CHMURA-KS3** | pobranie pliku z podpisanego URL magazynu KS3 (`XiaomiCloud.download`) |
| **MQTT** | `{region}-ha.mqtt.io.mi.com` (`cloud/mqtt.py:broker_host`), push z chmury, wymaga OAuth |
| **LOKALNIE→CHMURA** | najpierw lokalnie, przy błędzie fallback do chmury (tylko gdy wpis ma sesję chmurową) |
| **CHMURA→LOKALNIE** | odwrotnie: najpierw chmura, przy błędzie lokalnie |

Kluczowy punkt w kodzie: `__init__.py:async_setup_entry` tworzy `JonrMapCoordinator` **tylko gdy** `entry.data` ma
`CONF_SERVICE_TOKEN` (linia 156), a MQTT tylko gdy są pola OAuth (`_async_start_mqtt`, l. 234–246).
Wpis „Device IP & token” (`config_flow.py:async_step_local`, l. 151–180) zapisuje wyłącznie host, token, model i MAC,
więc **nie ma mapy, MQTT ani fallbacków chmurowych**.

## 1. Sterowanie podstawowe

| Funkcja | Kanał | MIoT | Kod |
|---|---|---|---|
| Start (całość) | LOKALNIE | stop 17.3, potem start-clean 17.1 `[1, "[]"]` | `device.py:start` → `_stop_and_settle`; `vacuum.py:async_start` |
| Pauza / wznowienie | LOKALNIE | 17.2 piid55 = 7 / 8 | `device.py:pause`, `start(activity="paused")` |
| Stop | LOKALNIE | 17.3 | `device.py:stop` |
| Powrót do stacji | LOKALNIE | 16.1 | `device.py:return_home` |
| Lokalizuj | LOKALNIE | 17.4 | `device.py:locate` |
| Moc ssania | LOKALNIE | odczyt 17.13, zapis akcją 17.26 | `device.py:set_fan_speed` → `_gear` |
| Poziom wody | LOKALNIE | odczyt 17.12, zapis 17.27 | `device.py:set_water_level` |
| Tryb pracy (odkurzanie/mop/custom) | LOKALNIE | odczyt 17.10, zapis 17.46 | `device.py:set_mode` |
| Liczba przejść | LOKALNIE | odczyt 17.14, zapis 17.28 | `device.py:set_count` |
| Trasa mopa | LOKALNIE | odczyt 17.65, zapis 17.50 | `device.py:set_route` |
| Głośność | LOKALNIE | odczyt 17.15, zapis 17.31 | `device.py:set_volume`; `number.py` |
| Sterowanie ręczne | LOKALNIE | 17.49 piid62 | `device.py:xtl_manual_control`; `vacuum.py:async_remote_control` |
| Szybkie mapowanie / mapowanie | LOKALNIE | 17.10 / 17.11 | `device.py:xtl_fast_building/xtl_clean_building`; `button.py` |

## 2. Sprzątanie pokoi i stref

| Funkcja | Kanał | MIoT | Kod |
|---|---|---|---|
| `clean_segment` (pokoje) | LOKALNIE | stop 17.3, potem 17.1 `[3, "[id,…]"]` | `vacuum.py:async_clean_segment` (bez fallbacku chmurowego, komentarz l. 253–255) → `device.py:clean_segments` → `room_clean_start_params` (profil nie ma `set_room_clean`, więc zawsze ścieżka start-clean typ 3) |
| `clean_zone` (strefy) | LOKALNIE | stop, potem 17.1 `[4, "[x1,y1,…×8]"]` | `vacuum.py:async_clean_zone` → `device.py:start_zone_clean`, `xtl.py:xtl_zone_flat` |
| `repeats` w obu | LOKALNIE | 17.28 | `vacuum.py:_apply_repeats` |
| `set_room_clean_mode` (ustawienia per pokój) | **LOKALNIE→CHMURA** + **wymaga mapy** | 17.53 piid70 (JSON) | `vacuum.py:async_set_room_clean_mode` → `_xtl_map_context` (rzuca błąd, gdy brak `runtime_data.map`) → `_xtl_write` |
| `reset_room_clean_modes` | LOKALNIE→CHMURA + wymaga mapy | 17.53 | `vacuum.py:async_reset_room_clean_modes` |
| `set_clean_sequence` (kolejność) | LOKALNIE→CHMURA + wymaga mapy (tylko `map_id`) | 17.53 typ 2 | `vacuum.py:async_set_clean_sequence` |
| `set_room_info` (nazwa/typ pokoju) | LOKALNIE→CHMURA + wymaga mapy | 17.15 piid60 | `vacuum.py:async_set_room_info` |

Komentarz autora przy `_xtl_write` (`vacuum.py` l. 286–289): *„17.53/17.15 are the plugin's cloud-side channels and
local writability is unverified on this firmware”*. **Lokalność zapisów 17.53/17.15 jest więc niepotwierdzona**
i wymaga testu w Etapie 2 i 3.

## 3. Ustawienia, DND, stacja, części

| Funkcja | Kanał | MIoT | Kod |
|---|---|---|---|
| Przełączniki (blokada, DND on/off, wznawianie, dywan boost/2x/najpierw, auto suszenie, auto detergent, ERP, mop+) | LOKALNIE | odczyt 17.x, zapis 17.24–17.56 | `device.py:_xtl_flag`; `switch.py:XtlSettingSwitch` |
| Selecty (preferencja dywanu, opróżnianie, czas suszenia, częstotliwość i temperatura mycia mopa) | LOKALNIE | 17.33/32/43/44/45 | `device.py:_xtl_select`; `select.py` |
| Okno DND: zapis | LOKALNIE (→CHMURA tylko w usłudze) | 17.30 piid18 | `vacuum.py:async_set_dnd_time` (`_xtl_write`), `time.py`, `switch.py:XtlDndFlagSwitch` (czysto lokalnie) |
| Okno DND: odczyt | LOKALNIE, ale **niewiarygodny** po zapisie | 17.19 | `device.py:status` (cache, l. 401–414), `xtl_note_dnd`. Autor: lokalny odczyt 17.19 po zapisie zwraca starą wartość, a „prawdę” daje push MQTT (`__init__.py` l. 279–286, 394–403) |
| Części eksploatacyjne: odczyt | LOKALNIE | 17.32 JSON | `device.py:_parse_xtl_consumables`; `sensor.py` |
| Części: reset | LOKALNIE | 17.20 piid33 | `device.py:reset_consumable`; `button.py:XtlConsumableResetButton` |
| Stacja: mycie / suszenie / opróżnianie (start/stop) | LOKALNIE | 17.40 / 17.41 / 17.42 (`true`/`false`) | `device.py:xtl_wash_mop…xtl_stop_collect_dust`; `switch.py:XtlStationSwitch`, `button.py` |
| Stan stacji (WashMop/HotDry/…) | LOKALNIE (poll) + MQTT (push) | 17.49 string | `device.py:status`; `__init__.py` l. 330–340, 432–442 |
| Zbiorniki / worek / mop – obecność | LOKALNIE | 17.51–17.54, 17.48 | `device.py:status` |
| Statystyki (sesja, łącznie) | LOKALNIE | 17.26/27/29/30/31 | `device.py:status` (`ext_narrow`) |
| Historia sprzątań | LOKALNIE (co 6. pełny poll) + MQTT | 17.46 JSON | `device.py:status` (`records`) |

## 4. Błędy i powiadomienia

| Funkcja | Kanał | MIoT | Kod |
|---|---|---|---|
| Błąd robota / stacji / komunikat | LOKALNIE (poll co 10 s) + MQTT (szybszy push) | 17.35 / 17.79 / 17.36 | `device.py:status`; `sensor.py`; `error_events.py` (zdarzenia `jonr_vac_error`) |
| Teksty błędów | LOKALNIE (pliki w integracji) | – | `xtl.py:XTL_ERROR_CODES`, `translations/` |

## 5. Harmonogramy i głosy

| Funkcja | Kanał | MIoT | Kod |
|---|---|---|---|
| Harmonogramy: odczyt | LOKALNIE (co 6. pełny poll) + MQTT | 17.17 JSON | `device.py:status` (`timers`); `sensor.py` (`xtl_timers_summary`) |
| Harmonogramy: nazwy pokoi i map w opisie | **wymaga mapy** | – | `sensor.py:_room_names/_map_names` (bez mapy pokazuje same ID) |
| Harmonogramy: edycja | **brak w integracji** | – | nie znaleziono akcji zapisu timerów |
| Wybór języka głosu | LOKALNIE | 17.21 piid61 | `device.py:set_voice_language` |
| Instalacja paczki głosowej | LOKALNIE (komenda) + **internet/LAN** (HA i robot pobierają plik z URL) | 17.21 | `device.py:install_voice_pack`, `fetch_voice_pack` (`urllib`); domyślne paczki leżą na CDN KS3 producenta |

## 6. Mapa (kluczowe)

| Funkcja | Kanał | MIoT / endpoint | Kod |
|---|---|---|---|
| Nazwa pliku bieżącej mapy | LOKALNIE | akcja 17.12 → out piid38 = `"uid/did/slot"` | `device.py:map_obj_name` |
| Nazwa pliku katalogu map | LOKALNIE | akcja 17.13 → out piid37 | `device.py:_xtl_map_list` (`last_map_infos_file`) |
| Podpisany URL do pliku | **CHMURA-API** | `/v2/home/get_interim_file_url_pro` (fallback `get_interim_file_url`) | `cloud/connector.py:map_url/_try_map_url`; `map.py:MapFetcher.fetch_obj` |
| Pobranie pliku mapy | **CHMURA-KS3** | URL z powyższego | `connector.py:download` |
| Dekodowanie i render PNG | LOKALNIE (czysty Python: JSON, base64, LZ4, Pillow) | – | `xtl_map.py:decode_map_file`, `render_xtl_map` |
| Katalog map i nazwy map | CHMURA-API + KS3 | plik map-infos | `map.py:fetch_map_infos`; `map_coordinator.py:_fetch_xtl` |
| Cykl odświeżania | CHMURA (poll 30 s przy sprzątaniu, 300 s w spoczynku) + MQTT (zdarzenia 17/e1, 17/e2) | – | `map_coordinator.py`, `const.py` l. 27–28 |
| Kopia mapy | LOKALNIE (HA `.storage/jonr_vac_map_cache_<entry_id>`) | – | `map_cache.py` (`Store`) |
| Usługa `refresh_map` | LOKALNIE (start i powrót) + CHMURA (oczekiwanie na upload) | – | `map_coordinator.py:async_refresh_map_with_movement` |
| Przełączanie map | **CHMURA→LOKALNIE** | 17.9 piid58; cloud `/miotspec/action` | `select.py` l. 212–259, `vacuum.py:_cloud_set_current_map`. Encja select istnieje tylko z map coordinatorem (`select.py` l. 83–91) |
| Kamera mapy / endpoint wektorowy / karta | wymaga map coordinatora | – | `camera.py` l. 23–25; `http_api.py` |
| Klucze szyfrowania | **nie dotyczy** | – | `map_coordinator.py:_build` docstring i `map_parsers.py`: pliki xtl to zwykły JSON, bez AES |

**Wniosek co do mapy:** robot sam generuje nazwę pliku i wysyła plik do chmury (KS3). Lokalnie da się dostać tylko
nazwę pliku, a sam plik leży w chmurze. Hipoteza do sprawdzenia w Etapie 2: czy jest lokalna komenda zwracająca
treść mapy lub listę pokoi. W kodzie takiej nie ma. Bez internetu robot prawdopodobnie nie wyśle nowej mapy, więc
kopia lokalna będzie aktualna tylko do momentu zmiany mapy w robocie.

## 7. Operacje, które potrzebują ID pokoi z mapy

| Operacja | Czego potrzebuje | Skąd bierze dziś |
|---|---|---|
| `clean_segment` | listy `room_id` | **Od użytkownika**: `vacuum.py` przekazuje je wprost do 17.1, nic nie sprawdza. Użytkownik bierze je z atrybutu `rooms` kamery mapy (`docs/SERVICES.md`). Bez mapy działa, jeśli znamy ID. |
| `set_room_clean_mode`, `reset_room_clean_modes`, `set_room_info` | `map_id` + lista pokoi (`room_id`, `prefer`, `name`, `type`) | `vacuum.py:_xtl_map_context` → `runtime_data.map.data.map_id` i `.attributes["rooms"]` (z pliku KS3, pole f3) |
| `set_clean_sequence` | `map_id` (+ ID od użytkownika) | jw. |
| `clean_zone` | współrzędne w układzie sceny mapy (siatka 5 cm) | od użytkownika; ramkę wyznacza mapa (kalibracja z `xtl_map.py:_calibration_points`) |
| Opis harmonogramów | `{room_id: name}`, nazwy map | `sensor.py:_room_names/_map_names` |
| Przełączanie map | ID zapisanych map | katalog z pliku map-infos (KS3) |

Definicja ID pokoju (`xtl_map.py:_normalize_areas`): z pliku mapy, pole f3, rekord `{id, room_id?, …}`.
**`room_id` = `room_id`, jeśli jest, w przeciwnym razie `id + 2`.** Atrybut `rooms` jest kluczowany przez `room_id`
i to on trafia do 17.1. `map_id` = `mapId` z nagłówka pliku.

Komentarz w `device.py:clean_segments` (l. 830–834) mówi, że ID z akcji `vacuum.start-room-sweep` (Mijia room id)
to coś innego niż ID mapy. Na xm2216 ta ścieżka nie jest używana.

## 8. Podsumowanie: co bez chmury przestanie działać (wg kodu)

1. Wszystko związane z mapą: kamera, karta, endpoint wektorowy, atrybut `rooms`, nazwy map, przełączanie map
   (select nie powstaje bez map coordinatora, choć sama komenda 17.9 ma ścieżkę lokalną).
2. Usługi per pokój (17.53/17.15): **blokuje je brak zapisanej mapy w HA**, a nie sam kanał. Do tego lokalny zapis
   jest niepotwierdzony.
3. Natychmiastowe aktualizacje z MQTT. Zostaje lokalny poll co 10 s; harmonogramy i historia co ~6 pełnych polli.
4. Wiarygodny odczyt okna DND po zmianie (odczyt 17.19 po lokalnym zapisie zwraca stare dane, według autora).
5. Instalacja paczek głosowych z CDN producenta (z LAN da się).

Wszystko pozostałe (start/stop, tryby, ssanie, woda, pokoje i strefy po ID, stacja, części, błędy, ustawienia) idzie
według kodu **lokalnie**. Nadal trzeba to potwierdzić testem przy odciętym internecie (Etap 3), bo możliwe, że firmware
robota sam odmawia pracy offline, czego kod nie pokaże.
