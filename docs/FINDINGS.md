# FINDINGS – lokalna wersja jonr-vac dla JONR P20 Pro

Dziennik ustaleń, prowadzony etapami. Każde twierdzenie o tym, co jest lokalne, a co chmurowe, ma dowód: plik/funkcję albo wynik testu.

## Etap 0: rozpoznanie (2026-11-06)

### Środowisko (stacja robocza)
- Python 3.15.0, git 2.56.0, pip 26.1.2. Brak `python-miio`/`miiocli` i `nmap`.
- PyPI jest osiągalne (`pip index versions python-miio` zwraca wersję 0.5.12 jako najnowszą stabilną).
  `genericmiot` istnieje tylko w gałęzi git python-miio, więc do etapu 2 potrzebny będzie venv z instalacją z git.
  Ryzyko: Python 3.15 jest bardzo nowy, a zależności python-miio mogą się nie zbudować. W razie problemów: venv z
  pythonem 3.12/3.13 (np. przez `uv`) albo kontener.
- Sieć: host <pc-ip>/24, brama <gateway>.

### Robot w sieci
- Broadcast miIO „hello” (UDP 54321) do <lan-broadcast>: odpowiedziało **jedno** urządzenie,
  `<robot-ip>`, device_id <did>. Pole tokenu z odpowiedzi celowo nie było wypisywane.
- Ping <robot-ip>: 3/3 odpowiedzi, MAC <mac>.
- **Niepotwierdzone**: że to jest P20 Pro. Potwierdzi to dopiero `miiocli ... info` z tokenem (model `xtl.vacuum.xm2216`).

### Repozytorium
- Sklonowano `moriceh/jonr-vac` (HEAD `e913dbb`) do `jonr-vac/`.
- `manifest.json`: `iot_class: cloud_push`, zależności `python-miio>=0.5.12`, `pycryptodome`, `paho-mqtt`.
- Kod chmurowy jest wydzielony w `custom_components/jonr_vac/cloud/` (`connector.py`, `mqtt.py`, `oauth.py`).
  Mapa: `map_coordinator.py`, `map_cache.py`, `xtl_map.py`, `map_parsers.py`, `camera.py`, `http_api.py`.
  Logika urządzenia: `device.py`, profil `spec/profiles/xtl.py`, a zdolności w `spec/capabilities/*`.
- Wg `docs/INSTALLATION.md` (twierdzenie autora, do weryfikacji w etapie 1): sterowanie zawsze idzie przez UDP
  lokalnie, a sesja chmurowa obsługuje mapę i „cloud command fallbacks (map switching, room writes)”.
  Mapa na żywo wymaga osobnej sesji MIoT **OAuth** i MQTT.
- Wg `docs/SERVICES.md`: ID pokoi (`segments`, `room_id`) pochodzą z atrybutu `rooms` kamery mapy, czyli z mapy chmurowej.
  To kluczowa zależność dla trybu lokalnego.
- Usługa `refresh_map` fizycznie wypuszcza robota ze stacji, żeby wymusić upload mapy. W trybie lokalnym trzeba to
  zastąpić pobraniem ostatniej mapy z chmury (bez ruchu robota).
- Istnieją testy (`tests/pure`, `tests/harness`), m.in. `test_xtl_map.py`, które przydadzą się w etapie 6.

### Zmiany w repo
- `.gitignore`: dodano `.env*`, `secrets.yaml`, `*.token`, `local_data/`, `map_dumps/`.

### Otwarte
- Potwierdzenie IP robota, token, adres HA i sposób testowania (patrz pytania w czacie).

### Etap 0b: pozyskanie tokenu (2026-11-06)
- Użytkownik potwierdził IP robota: <robot-ip>. Region konta nieznany (prawdopodobnie `de`), więc skrypt przeszukuje wszystkie.
- Ekstraktor `PiotrMachowski/Xiaomi-cloud-tokens-extractor` (commit `c4db715`, MIT) sklonowany do `../third_party/`.
  Przegląd kodu: łączy się wyłącznie z `account.xiaomi.com`, `sts.api.io.mi.com`, `{region.}api.io.mi.com`, a dla
  QR/captchy uruchamia lokalny serwer HTTP na :31415. Domyślny poziom logów CRITICAL, haseł nie zapisuje.
  Wada: wypisuje tokeny wszystkich urządzeń na stdout.
- Dlatego powstały `tools/get_token.py` (nakładka: używa logowania ekstraktora, zapisuje do `.env` (0600) tylko token
  `xtl.vacuum.xm2216`, nic nie wypisuje) i `tools/envfile.py` (zapis sekretów z ukrytym wejściem).
- venv: `../.venv` (Python 3.15). Zależności ekstraktora zainstalowały się bez problemów.
- HA: Dell Wyse 5070 (sposób instalacji HA do potwierdzenia). Token HA trafi do `.env` jako `HA_TOKEN`.
- HA: `http://<ha-ip>:8123`, wersja 2026.10.4, komponent `hassio` obecny (HAOS lub Supervised),
  `jonr_vac` już zainstalowany i załadowany. Weryfikacja wyłącznie przez odczyt `GET /api/` i `/api/config`.
- Pierwsza próba logowania QR (20:24–20:29): kod wygasł po ok. 5 min bez skanowania. Ponowiona.
- Druga próba QR (20:30): sukces. Konto w regionie **`de`**, jedno urządzenie `xtl.vacuum.xm2216` („Robot”),
  IP <robot-ip>, did <did>. Token zapisany w `.env` (0600), nigdzie nie wyświetlany.
- **Dowód lokalnego dostępu**: `tools/miio_probe.py miIO.info` (własny, minimalny klient miIO, tylko odczyt, bez chmury)
  zwraca `model=xtl.vacuum.xm2216`, `fw_ver=4.5.6_0805`, `miio_ver=0.1.0`, RSSI −59 dBm. Token jest poprawny.
- Uwaga: `tools/get_token.py` został zmieniony poza sesją (20:30:48). Wywołuje `make_qr_connector(te)`, której definicji
  w pliku brak, więc ścieżka QR zakończy się `NameError`. Token jest już pozyskany, więc nie blokuje to dalszej pracy.
- Logowanie QR ekstraktora (`login_step_1`: samo `longPolling/loginUrl`) dawało kod odrzucany przez Mi Home.
  `tools/get_token.py` dostał `make_qr_connector()`: pełny przepływ jak `cloud/connector.py::qr_begin`
  (najpierw `serviceLogin` → `_sign`/`serviceParam`, potem `loginUrl` ze wszystkimi polami, UA Mi Home). Działa (2026-11-06).
- Wynik: robot „Robot”, `xtl.vacuum.xm2216`, region **de**, IP <robot-ip>, did <did> → potwierdzone, że to P20 Pro.
  Token zapisany w `.env` jako `MIIO_TOKEN` (+ `MIIO_IP`, `MIIO_DID`, `MIIO_MODEL`, `XIAOMI_SERVER`).

## Etap 1: audyt kodu, lokalnie czy chmura (2026-11-06)

Pełna tabela: `docs/LOCAL_VS_CLOUD.md`. Najważniejsze:
- **Lokalnie wg kodu** (UDP, `device.py`): start/pauza/stop/dok, ssanie, woda, tryb, przejścia, trasa, głośność,
  sprzątanie pokoi (17.1 typ 3 + ID) i stref (17.1 typ 4), stacja (17.40–42), części (17.32 / reset 17.20),
  błędy (17.35/17.79/17.36), przełączniki i selecty ustawień, odczyt harmonogramów (17.17) i historii (17.46).
- **Chmura**: plik mapy i katalog map (lokalnie tylko nazwa pliku z 17.12/17.13, a URL i pobranie przez
  `get_interim_file_url_pro` + KS3), MQTT (push stanu i zdarzeń mapy), fallback zapisów 17.53/17.15/17.30,
  przełączanie map w pierwszej kolejności przez chmurę.
- **Pliki mapy xtl nie są szyfrowane** (JSON + base64 + LZ4). Zapisaną kopię da się renderować w pełni offline
  (`xtl_map.py`).
- Usługi per pokój są zablokowane w trybie lokalnym, bo wymagają `runtime_data.map`, a nie dlatego, że wymagają
  chmury. Zapisana mapa rozwiąże to w Etapie 5. Lokalność zapisu 17.53/17.15 jest niepotwierdzona (komentarz autora).
- `room_id` = `room_id` z pola f3 pliku mapy albo `id + 2`. To ID idzie do 17.1.

Stan obecnej instalacji HA (tylko odczyt REST API):
- Dwa wpisy `jonr_vac`: „Jonr P20 Pro” w stanie **loaded** oraz drugi, również „Jonr P20 Pro”, w stanie
  **not_loaded**. Do wyjaśnienia (duplikat?).
- Aktywny wpis ma mapę (tryb chmurowy): `camera.jonr_p20_pro_mapa`, mapa „Parter” (jedyna).
- Pokoje (room_id → nazwa): **3 Salon, 4 Jadalnia, 5 Kuchnia, 6 Korytarz, 7 Łazienka** (id f3 = room_id − 2,
  zgodnie z regułą).
- `sensor.jonr_p20_pro_harmonogramy_sprzatania` = `unknown`, czyli 17.17 jeszcze nieodczytane albo puste. Ważne
  dla wątku o pomijanych pokojach.

## Etap 2: sonda lokalna (2026-11-06)

Pełna tabela: `docs/MIOT_SPEC.md` (spec v4 z miot-spec.org i kolumna z wynikiem lokalnego odczytu).
- `python-miio` 0.6.0.dev0 (git) zainstalował się na Pythonie 3.15 w `../.venv`. Narzędzia czytają IP i token z
  `.env`, więc token nie pojawia się w linii poleceń. Surowe zrzuty trafiają do `local_data/` (w `.gitignore`).
- Model ma usługi siid 1, 2, 16, 17 (77 właściwości, 56 akcji, 3 zdarzenia) i 7 (bit-test).
- **Lokalnie OK**: stan (2.2 = 13 Charged), bateria, wszystkie ustawienia 17.x, części (17.32), błędy (17.35, 17.79),
  stacja (17.49 `ChargeAsleep`, 17.48, 17.51–54), statystyki, DND (17.19), cel bieżącego zadania (17.34 clean-values,
  teraz `[]`), typ zadania (17.9).
- **Lokalnie brak**: treść mapy, lista pokoi, pozycja robota. Akcje 17.12/17.13 zwracają wyłącznie nazwy plików
  KS3 (`<uid>/<did>/0` i `/1`). Starsze komendy miIO z innych robotów są ignorowane. Na robocie nie ma otwartych
  typowych portów TCP. **Wniosek (z dowodem): mapę można dostać tylko z chmury.**
- 17.46 (historia sprzątań) lokalnie nie odpowiada wcale. Diagnostyka „co posprzątano” musi więc opierać się na
  17.34 (cel zadania) i 17.9 (typ) w trakcie pracy, a nie na historii.
- **17.17 harmonogramy = `[]`**: robot nie ma żadnego zapisanego harmonogramu. „Codzienne” sprzątanie z aplikacji
  jest więc najpewniej automatyzacją/sceną Mi Home (chmura), a nie timerem w robocie. Do potwierdzenia z
  użytkownikiem. To istotne, bo po odcięciu internetu takie sprzątanie przestanie się uruchamiać.
- Spec ma 17.16 `set-schedule-timer` (zapis harmonogramu do robota), którego integracja nie używa. To potencjalna
  droga do harmonogramów niezależnych od chmury, choć prościej robić je automatyzacją HA.

### Etap 2b: testy komend (2026-11-06, za zgodą)
- **A pokój 6** i **B strefa 1×1 m** działają lokalnie. Robot raportuje 17.9 Area/Zone Clean i 17.34 z celem.
- **C1 17.15** (nazwa pokoju) lokalnie: `-9999 user ack timeout` w obu próbach. Po komendzie robot przechodzi w
  Idle; w trakcie powrotu do stacji przerwał go (ponowiono 16.1, robot wrócił). **Nie używać lokalnie.**
- **C2 17.53** (ustawienia pokoju) lokalnie: code 0. Efekt niewidoczny, bo zapisano te same wartości.
- Robot po testach: w stacji, 13 Charged, bez błędów.
- `map_id` aktywnej mapy „Parter” = 1.

## Etap 3: test bez internetu (2026-11-06)
- Użytkownik zablokował robotowi internet na routerze. **Mi Home pokazuje robota jako offline**, więc blokada jest
  potwierdzona.
- T0 (21:23): **21/21 operacji OK** lokalnie (szczegóły w `docs/OFFLINE_TEST.md`). T30 w toku.
- Decyzja użytkownika: mapę (z nazwami pokoi) robi w Mi Home przy chwilowo odblokowanym robocie, a **wszystko
  inne ma działać lokalnie**.

## Wątek dodatkowy: pomijane pokoje (odczyt historii HA, tylko do odczytu)
- Codzienne sprzątanie to **automatyzacja HA** `automation.sprzatanie_robot`: trigger 02:00, akcja
  `vacuum.start` (sprzątanie całego domu, robot sam wybiera trasę), brak warunków.
- Przebieg nocy (czas UTC, lokalny = +1 h): sprzątanie w odcinkach ~10–13 min z powrotem do stacji między nimi
  (mycie mopa, 17.23 = co 10 min). Liczba odcinków: 03.11: 5 (+33 m²), 04.11: 4 (+30 m²), 05.11: 3 (+25 m²).
  **06.11: automatyzacja się uruchomiła (last_triggered 01:00Z), ale robot nie wystartował** (cała noc `docked`).
- Bateria w nocy nie spada poniżej 89 %, więc to nie jest przyczyna (wyłączone „wznów sprzątanie” nie gra tu roli).
- Log błędów HA nie ma wpisów z nocy (HA restartował 06.11 ok. 19:33Z).
- Hipotezy do sprawdzenia diagnostyką z Etapu 5 (log 17.34/17.9/2.2 w trakcie zadania): (a) robot kończy
  „cały dom” po powrocie z mycia mopa, gubiąc niedokończone pokoje; (b) problem z relokalizacją po wyjeździe ze
  stacji (w testach widać stan 17 Relocation za każdym razem); (c) zamknięte drzwi. Pewna naprawa niezależna od
  przyczyny: automatyzacja z jawną listą pokoi (`clean_segment [3,4,5,6,7]`) i sprawdzenie po zakończeniu,
  które pokoje zostały wykonane.
- T15 (21:35, ~15 min offline, skrócone z 30 min na prośbę użytkownika): **21/21 OK**. **Etap 3 zamknięty.**

## Etap 4: jednorazowy zrzut mapy (2026-11-06)
- `tools/dump_map.py`: nazwy plików pobiera lokalnie z robota (17.12 / 17.13), plik i katalog map z chmury jeden raz
  (`get_interim_file_url_pro` + KS3), sesję trzyma tylko w pamięci. Logowanie przez QR ekstraktora, bo QR z kodu
  integracji (`XiaomiCloud.qr_begin/qr_poll`) nie dokończył logowania. Sesja jest przekazywana do
  `XiaomiCloud.restore_session`, a pobranie i dekodowanie to kod integracji (`connector.map_url/download`,
  `xtl_map.render_xtl_map`, `xtl_parse_map_infos_*`).
- **Robot nie potrzebował internetu**: plik był w KS3 od ostatniego uploadu sprzed blokady. Blokada nie była zdejmowana.
- Zrzut: `local_data/map_dumps/20261106-214337/` (+ `latest`): `map_raw.json` (8 kB), `map_infos_raw.json`,
  `meta.json`, `rooms.json`, `calibration.json`, `attributes.json`, `vector.json`, `map.png`. W plikach nie ma
  did ani tokenów (grep).
- `tools/render_map.py`: render z kopii przy zablokowanych gniazdach sieciowych w procesie daje **plik bajtowo
  identyczny** z pierwszym renderem. PNG 776×704 jest wizualnie identyczny z obrazem `camera.jonr_p20_pro_mapa` z HA.
- Mapa: `map_id` 1 „Parter” (jedyna w katalogu). Pokoje (room_id, powierzchnia z rastra):
  3 Salon ~11,9 m², 4 Jadalnia ~10,1 m², 5 Kuchnia ~3,1 m², 6 Korytarz ~10,0 m², 7 Łazienka ~4,5 m²;
  razem ~39,6 m². Wszystkie pokoje: `order` 0 (brak własnej kolejności), ustawienia domyślne.
- Wątek pomijanych pokoi: nocne sprzątania dawały +25…35 m² przy ~40 m² podłogi, więc w gorsze noce brakowało
  ~⅓ powierzchni.
- Do zrobienia w integracji (Etap 5): ręczne „odśwież mapę z chmury”, domyślnie wyłączone, bez MQTT.
- Uwaga kosmetyczna: renderer koloruje kilka sąsiednich pokoi tym samym odcieniem (tak samo jak w HA). Nie ma
  wpływu na ID ani na sterowanie.

## Etap 5: tryb „lokalnie + zapisana mapa” (2026-11-06, w toku; kod gotowy, niewdrożony)
Gałąź `local-saved-map`, bez commitów. Zmiany:
- `config_flow.py`: nowa opcja menu `local_map` (IP + token + nazwa, domyślnie „Jonr P20 Pro”). Wpis dostaje
  `map_mode: saved`, bez żadnych danych chmurowych. `unique_id` = MAC, jak w pozostałych ścieżkach.
- `saved_map.py` (nowy): `SavedMapCoordinator` z tym samym interfejsem co koordynator chmurowy (`.data`,
  `.map_list_meta`, `.device`). Kopia mapy leży w HA Store `jonr_vac_saved_map_<entry_id>`. Render przez
  `xtl_map` (0,04 s), bez pollingu i bez sieci.
- `__init__.py`: w trybie saved **nie powstaje** `JonrMapCoordinator`, `XiaomiCloud` ani `MiotMqttClient`.
- Usługa `jonr_vac.import_map` (zwraca podsumowanie) + `tools/push_map.py` (wysyła zrzut przez REST API HA).
- `clean_segment` odrzuca ID spoza zapisanej mapy (z podpowiedzią, by odświeżyć mapę). `set_room_info` jest
  zablokowane w trybie lokalnym (17.15 psuje zadanie robota, Etap 2b). `refresh_map` odsyła do
  `dump_map.py`. Zapis 17.53 jest odzwierciedlany w kopii mapy (`prefer`).
- Wybór mapy (select) jest wyłączony w trybie saved (jedna zapisana mapa).
- `clean_log.py` (nowy): log zadań z 17.9/17.34/17.27/2.2, zdarzenie `jonr_vac_clean_finished`, sensor
  „Ostatnie sprzątanie” (pokrycie % = powierzchnia robota / powierzchnia pokoi docelowych z mapy), historia 30
  zadań w Store, Repairs „zapisana mapa nieaktualna”, gdy robot zgłosi nieznane ID pokoju.
- **Poprawiony błąd upstream**: `vacuum._xtl_map_context` robił `list()` ze słownika `rooms`, przez co
  `set_room_clean_mode`, `reset_room_clean_modes` i `set_room_info` padały z `AttributeError` także w trybie
  chmurowym.
- Tłumaczenia: en, pl (pełne), pozostałe języki z tekstem angielskim (test kompletności kluczy).

Testy (testowy HA 2026.10.4 w `../.venv-ha`, pytest-homeassistant-custom-component, gniazda sieciowe wyłączone):
- `tests/harness/test_saved_map.py`: 3 testy (pełna ścieżka: setup bez chmury, import, kamera, clean_segment
  17.1, odrzucenie nieznanego ID, blokada 17.15, 17.53 + odbicie w kopii, odmowa refresh_map, trwałość po reload,
  `XiaomiCloud`/MQTT nigdy nie konstruowane; log sprzątania; config flow). Mapa w testach jest syntetyczna.
- Cały zestaw: przed zmianami 373 OK / 31 FAIL / 2 ERROR, po zmianach **376 OK / 31 FAIL / 2 ERROR**, bez nowych
  niepowodzeń. Istniejące niepowodzenia pochodzą z upstream (testy profili dreame/ijai usuniętych z kodu,
  przestarzałe pole `door_state_raw`, brak `import pytest`).

### Etap 5b: wdrożenie na HA użytkownika (2026-11-06 22:00–22:20, po kopii zapasowej użytkownika)
- Pliki przez SSH (dodatek, klucz użytkownika, za jego zgodą). Stara wersja jest w
  `/config/backup_jonr/jonr_vac-upstream-20261106-2200`. `check_config` = valid przed każdym restartem.
- Usunięto oba stare wpisy `jonr_vac` (chmurowy i wyłączony). Dodano wpis `local_map` przez REST config flow
  (token z `.env`, niewyświetlany): „Jonr P20 Pro”, `entry_id <entry_id>M`. **Encja
  `vacuum.jonr_p20_pro` zachowała nazwę**, więc automatyzacja „Sprzątanie robot” trafia w nią dalej. Sensor logu
  przemianowano z `sensor.kuchnia_jonr_p20_pro_ostatnie_sprzatanie` (obszar „Kuchnia” odziedziczony po starym
  urządzeniu) na `sensor.jonr_p20_pro_ostatnie_sprzatanie`.
- `tools/push_map.py` → `import_map`: map_id 1 „Parter”, 5 pokoi, sha256 zgodny ze zrzutem. Mapa przetrwała restart.
- Test na żywo przez HA (robot offline): `clean_segment [9]` odrzucone z komunikatem; `clean_segment [6]`, robot
  sprząta; `return_to_base` OK.
- **Odkrycie**: po samym `return_to_base` (16.1) zadanie zostaje otwarte (2.2 = 13 Charged, 17.9 = 9 Area Pause,
  17.34 = `[6]`), więc „Idle” nie przychodzi. Log kończy teraz sesję także po 10 min postoju w stacji z
  wstrzymanym zadaniem (myjka mopa w nocy trwa ~2 min, więc tego nie przerwie) albo po zmianie zadania.
  Pokrywa to 9 testów jednostkowych `tests/pure/test_clean_log.py`.
- Test logu na żywo: `clean_segment [6]` → `vacuum.stop` → wpis {kind rooms, rooms [Korytarz], expected 10 m²,
  area 0 m², end_status 1}. **17.26 liczy sekundy** (21 po ~25 s pracy), stąd pole `robot_clean_time_s`.
- Log systemowy HA (websocket `system_log/list`) bez wpisów jonr/xiaomi/miot/mqtt; brak zgłoszeń Repairs `jonr_vac`.
  Próba wglądu w połączenia HA przez SSH nic nie daje (dodatek ma własną sieć kontenera). Dowodem braku połączeń z
  chmurą pozostają: ścieżka kodu, test harness z wyłączonymi gniazdami i brak wpisów w logach.
- Testy: **385 OK / 31 FAIL / 2 ERROR** (bez nowych niepowodzeń względem upstream 373/31/2).
- HACS pokazuje `update.jonr_vacuum_update`. **Nie aktualizować** jonr-vac w HACS, bo nadpisze fork.

## Etap 6: testy, dokumentacja, bezpieczeństwo (2026-11-06)
- Testy dodane w forku: `tests/pure/test_clean_log.py` (9: sesje, pokrycie, mycie mopa, wstrzymanie w stacji,
  start z wstrzymanym zadaniem, podmiana zadania, nieznane ID, błędy) i `tests/harness/test_saved_map.py`
  (8: setup bez chmury, import, kamera, room-clean, blokady, trwałość, config flow; parser mapy i mapowanie pokoi
  `room_id`/`id+2`, katalog, nadpisania `prefer`, odrzucanie śmieci). Wszystkie dane testowe są syntetyczne.
- Wynik końcowy: **390 OK / 31 FAIL / 2 ERROR** wobec upstream 373 / 31 / 2. **Zero nowych niepowodzeń.**
  Niepowodzenia upstream (testy usuniętych profili, `door_state_raw`, brak `import pytest`) zostawiono bez zmian.
- Dokumentacja: `docs/LOCAL_MODE.md` (nowy), README (sekcja forka, tabela dokumentów, ścieżki konfiguracji),
  `docs/SERVICES.md` (`import_map`), `docs/ENTITIES.md` (sensor logu), `CREDITS.md` (fork, ekstraktor MIT, kopia
  spec MIoT, python-miio w narzędziach).
- Bezpieczeństwo:
  - Skan 218 plików widocznych dla gita: token robota i token HA **nie występują nigdzie**. did i MAC zastąpiono
    w dokumentach znacznikami `<did>` / `<mac>`.
  - `.env`, `local_data/` (zrzuty map, odczyty, kopia automatyzacji) są ignorowane (`git check-ignore`).
  - Logi integracji nie zawierają tokenów (grep `_LOGGER`). **Poprawka**: `tools/miio_probe.py` wypisywał pełną
    odpowiedź `miIO.info`, zawierającą token urządzenia. Teraz maskuje token, MAC, uid, SSID/BSSID i IP.
    Wcześniej token nie wyciekł, bo wywołania szły zawsze przez filtr.
  - Licencje: `LICENSE` i `LICENSE.xiaomi-vac` bez zmian. Nic nie jest vendorowane (ekstraktor jest ładowany z
    `../third_party/`, python-miio to zależność).
- Pliki integracji na HA są identyczne z repo (md5 wszystkich plików).
- Usunięto testowe środowisko HA `../.venv-ha` (prośba użytkownika). Zostają `../.venv` (narzędzia: dump, push,
  sondy) i `../third_party/` (ekstraktor), potrzebne do odświeżania mapy.
- Po stronie użytkownika zostaje zmiana automatyzacji „Sprzątanie robot” na `jonr_vac.clean_segment [3,4,5,6,7]`
  (zapis konfiguracji HA zablokowany przez uprawnienia Claude Code); YAML w `docs/LOCAL_MODE.md`.

## Etap 7: osobna integracja „JONR Local” (2026-11-06 22:35–22:50)
Użytkownik oczekiwał nowej integracji, a nie podmienionego `jonr_vac`. Zrobiono:
- Repo `jonr-local/` (kopia forka z historią, gałąź `jonr-local`). Poprzedni, niedokończony folder `jonr-local`
  (sama zmiana nazwy, bez trybu lokalnego) przeniesiono do `../_archive/jonr-local-old-20261106`, wcześniej
  usuwając z niego duplikat `.env`. `.env` i `local_data/` przeniesiono (nie skopiowano) do `jonr-local/`, więc
  sekrety istnieją w jednym miejscu.
- Domena `jonr_local`, nazwa „JONR Local”, wersja `0.1.0+local.1`, `iot_class: local_polling`. Usługi
  `jonr_local.*`, zdarzenia `jonr_local_*`, karta pod `/jonr-local-card`, endpoint `/api/jonr_local/map/…`. Nazwa
  `jonr_vac` nie występuje już w kodzie, testach ani narzędziach.
- `saved_map.py`: brak zaimportowanej mapy przy starcie to teraz jednorazowe ostrzeżenie zamiast ERROR (bez
  odświeżania koordynatora).
- Testy: **390 OK / 31 FAIL / 2 ERROR**, bez nowych niepowodzeń względem upstream.
- HA: usunięto wpis `jonr_vac`. Pliki `jonr_vac` (fork) przeniesiono do `/config/backup_jonr/jonr_vac-fork-*`.
  Wgrano `custom_components/jonr_local`, dodano wpis „Jonr P20 Pro” (`local_map`) przez REST flow, mapę
  zaimportowano (sha256 zgodny). Encje: `vacuum.jonr_p20_pro`, `camera.jonr_p20_pro_mapa`,
  `sensor.jonr_p20_pro_ostatnie_sprzatanie` (59 encji, bez przedrostka obszaru; urządzenie nie ma przypisanego
  obszaru).
- Test na żywo: `jonr_local.clean_segment [9]` odrzucone; `[6]`, potem stop: wpis logu {rooms [Korytarz], expected
  10 m², robot_clean_time_s 11}; powrót do stacji OK. Log systemowy bez wpisów jonr/xiaomi/mqtt.
- Zablokowane przez uprawnienia (do zrobienia przez użytkownika): usunięcie starego zasobu Lovelace
  `/jonr-vac-card/xiaomi-vac-card.js` (teraz 404) i zmiana automatyzacji na `jonr_local.clean_segment`. HACS:
  usunąć pozycję „JONR Vacuum” (jej pliki są już przeniesione).

### Etap 7b: uprawnienia i dokończenie (2026-11-06 22:47)
- Na prośbę użytkownika dodano wąską regułę uprawnień Claude Code (`.claude/settings.local.json` w katalogu
  projektu): `Bash(.venv/bin/python jonr-local/tools/ha_admin.py *)`. Narzędzie `tools/ha_admin.py` umie tylko:
  status, deploy (z kopią), check-config, restart, odczyt i zapis automatyzacji (z kopią w `local_data/`), listę i
  usuwanie zasobów Lovelace oraz zmianę entity_id.
- Usunięto zasób Lovelace `/jonr-vac-card/xiaomi-vac-card.js`.
- Automatyzacja „Sprzątanie robot” (02:00) wywołuje teraz `jonr_local.clean_segment [3,4,5,6,7]`. Poprzednia
  wersja (`vacuum.start`) leży w `local_data/automation_<automation_id>_20261106-224710.json`.
- Po stronie użytkownika zostaje tylko usunięcie pozycji „JONR Vacuum” w HACS.
- 23:17: urządzenie przypisano do obszaru „kuchnia” (`ha_admin.py device-area`). Na pulpit `<dashboard>`
  dopisano 6 sekcji robota (69 kart: mapa `custom:xiaomi-vac-card`, przyciski pokoi z potwierdzeniem, tryb, stacja,
  części z resetem, ustawienia i statystyki). Wszystkie encje zweryfikowane z rejestrem. Poprzednia konfiguracja
  pulpitu jest w `local_data/dashboard_<name>_<ts>.json`.

### Etap 8: pokoje głosem — natywne „clean area” (v0.3.1, 2026-11-07)
- Objaw: „Ok Google, odkurz kuchnię” uruchamiało sprzątanie całego domu. Logbook 07:44:18 UTC: Google wysłał
  tylko `StartStop`, bez strefy → `vacuum.start`.
- Przyczyna (kod HA 2026.10.4, `google_assistant/trait.py`): Google dostaje `availableZones` i zamienia strefę na
  `vacuum.clean_area` tylko wtedy, gdy encja ma `VacuumEntityFeature.CLEAN_AREA` i mapowanie obszarów
  (`area_mapping` w opcjach encji). `vacuum.jonr_p20_pro` miał `supported_features` 12828, bez CLEAN_AREA (16384).
- Zmiana: `vacuum.py` zgłasza CLEAN_AREA (gdy jest mapa), `async_get_segments` (id `"<map_id>_<room_id>"`,
  `group` = nazwa piętra przy >1 piętrze), `async_clean_segments` → istniejące `async_clean_segment`; pokoje
  z innego piętra są odrzucane; zmiana pokoi vs `last_seen_segments` → naprawa HA „segments changed”. Na HA bez
  CLEAN_AREA kod jest nieaktywny.
- Test `test_clean_area_maps_areas_to_rooms`: lista segmentów przez WS `vacuum/get_segments`, mapowanie obszaru,
  `vacuum.clean_area` → 17.1 typ 3 `[4]` (żadnego startu całego domu), odmowa innego piętra, naprawa.
  Cały zestaw: 400 OK / 30 FAIL / 2 ERROR; zestaw niepowodzeń identyczny jak bez zmiany (stare testy upstream).
