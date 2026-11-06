# Test odcięcia od internetu (Etap 3)

**Konfiguracja:** robot (`<robot-ip>`, MAC `<mac>`) ma zablokowany ruch do internetu na routerze
(użytkownik, 2026-11-06 ok. 21:20). Ruch w LAN pozostaje otwarty. HA nie jest blokowany, bo testy idą z
komputera `<pc-ip>` skryptem `tools/offline_test.py`. Surowe wyniki leżą w `local_data/offline_*.json`.

**Potwierdzenie blokady:** ✅ użytkownik potwierdził, że Mi Home pokazuje robota jako **offline**.

## Przebieg T0 (zaraz po blokadzie, 21:23)

Wszystkie zapisy wysyłały obecną wartość albo były od razu odwracane. Pominięto operacje niszczące (reset części,
przełączenie i usunięcie mapy).

| operacja | rodzaj | wynik | szczegóły |
|---|---|---|---|
| miIO.info | odczyt | ✅ | model xtl.vacuum.xm2216 |
| stan / bateria / błędy (2.2, 16.1, 17.35, 17.79, 17.36) | odczyt | ✅ | 13, 100, 0, 0, 0 |
| tryby (17.10, 17.12, 17.13, 17.14, 17.65) | odczyt | ✅ | |
| części (17.32) | odczyt | ✅ | 7 pozycji |
| stacja (17.49, 17.48, 17.51–54) | odczyt | ✅ | ChargeAsleep … |
| DND (17.19), harmonogramy (17.17) | odczyt | ✅ | 17.17 = `[]` |
| nazwa pliku mapy (17.12) | akcja-odczyt | ✅ | `<uid>/<did>/0` |
| nazwa katalogu map (17.13) | akcja-odczyt | ✅ | `<uid>/<did>/1` |
| moc ssania (17.26), woda (17.27), tryb (17.46), głośność (17.31) | zapis | ✅ | code 0 |
| blokada rodzicielska przełącz i przywróć (17.36) | zapis | ✅ | 0→1→0 potwierdzone odczytem |
| okno DND (17.30) | zapis | ✅ | code 0 |
| ustawienia pokoju 6 (17.53) | zapis | ✅ | code 0 |
| lokalizuj (17.4) | akcja | ✅ | |
| stacja: suszenie start/stop (17.41) | akcja | ✅ | 17.49: HotDry → ChargeAsleep |
| sprzątanie pokoju 6 (17.1 typ 3) | ruch | ✅ | 17.9 = 8, 17.34 = `[6]` |
| powrót do stacji (16.1) | ruch | ✅ | |
| sprzątanie strefy 1×1 m (17.1 typ 4) | ruch | ✅ | 17.9 = 11, 17.34 = współrzędne |
| powrót do stacji (16.1) | ruch | ✅ | |

**Wynik: 21/21 OK.**

## Przebieg T15 (ok. 15 min po blokadzie, 21:35)

Na prośbę użytkownika drugi przebieg zrobiono po ok. 15 min zamiast 30. Lista operacji ta sama co w T0.
**Wynik: 21/21 OK** (`local_data/offline_T15_*.json`). Czasy odpowiedzi bez zmian (≤ 0,1 s dla odczytów i zapisów).

**Wniosek:** wszystkie lokalne funkcje z Etapu 1 działają bez internetu, także po kilkunastu minutach od odcięcia.
Nie sprawdzono wielogodzinnej pracy offline; to wyjdzie w praktyce po Etapie 5 (nocna automatyzacja).

## Funkcje wymagające chmury i propozycje

Na podstawie Etapów 1–3. Testem odcięcia nie da się sprawdzić tego, co i tak wymaga chmury z założenia
(pobranie pliku mapy z KS3, MQTT).

| Funkcja | Dlaczego chmura | Propozycja |
|---|---|---|
| Pobranie mapy (plik KS3) | treść mapy istnieje tylko w chmurze; robot lokalnie podaje nazwę pliku (Etap 2) | **Obejść**: jednorazowy zrzut i kopia lokalna (Etap 4). Ręczne „odśwież z chmury”, domyślnie wyłączone |
| Aktualizacja mapy po zmianach w robocie (nowe pokoje, podział, przemeblowanie) | robot wysyła nowy plik do KS3; offline nie wyśle | **Opcjonalne**: na czas odświeżenia odblokować robota, przebudować lub zapisać mapę, pobrać zrzut, zablokować ponownie |
| Pozycja robota na żywo, trasa | tylko w pliku mapy (pole f2/f1) | **Zrezygnować**. Zostaje stan z 17.9 / 17.34 / 2.2 |
| MQTT (natychmiastowe aktualizacje) | broker Xiaomi | **Zrezygnować**. Lokalny poll co 10 s wystarczy |
| Przełączanie map w HA | integracja woli chmurę; lokalnie 17.9 istnieje | **Lokalnie** (do testu przy drugiej mapie). Jest tylko jedna mapa, więc niski priorytet |
| Zmiana nazwy / typu pokoju (17.15) | lokalnie `-9999` i zakłóca zadanie (Etap 2b) | **Zrezygnować** w trybie lokalnym (zmieniać w Mi Home przy odblokowanym robocie, potem odświeżyć zrzut). Nazwy i tak trzymamy w lokalnej kopii |
| Historia sprzątań (17.46) | lokalnie bez odpowiedzi (prawdopodobnie za duża odpowiedź UDP) | **Obejść**: log w HA na podstawie 17.34 / 17.9 / statystyk sesji |
| Harmonogram „codzienny” | robot nie ma timerów (17.17 = `[]`), najpewniej scena w chmurze Mi Home | **Obejść**: automatyzacja HA z jawną listą pokoi (wątek dodatkowy) |
| Paczki głosowe z CDN producenta | pobierane z internetu | **Opcjonalne**: serwować z LAN (integracja to wspiera) |
| Aktualizacje firmware | chmura | świadomie bez nich, ewentualnie okresowo odblokować |
