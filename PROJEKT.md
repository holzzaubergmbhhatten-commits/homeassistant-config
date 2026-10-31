# Touchmonitor-Dashboard im Flur

Projektstand, damit wir in jeder neuen Sitzung direkt weitermachen können.

## Ziel
27"-Touchmonitor an der Wand im Flur: Kalender/Buchungen, Wetter,
Amazon-Kachel, Einkaufsliste, Smart-Home (Lichter, Tor), später Grundriss
zum Antippen einzelner Räume.

## Hardware
- Monitor: iiyama ProLite T2755MSC-B1 (27", Full-HD, kapazitiver Touch, HDMI + USB)
- Rechner: kleiner Firmen-PC mit **Home Assistant OS**, Adresse `http://192.168.0.191:8123`
  (Backup vom Laptop am 27.09.2026 wiederhergestellt). Netzwerk: TP-Link Omada.
  Vorher Testphase auf Windows-Laptop mit Docker.

## Entscheidungen
- Plattform: Home Assistant (statt iPad)
- Kalender: eigene Website (Direktbuchungen) + Holidu + lokaler Geburtstage-Kalender
- Wetter: Met.no
- Amazon: Verknüpfungs-Kachel (öffnet Amazon im eigenen Fenster)
- Einkaufsliste: To-do-Karte
- Shelly: native Integration (lokal, parallel zu Apple Home) – Hoftor drin
- IKEA: Dirigera-Hub über HACS-Community-Integration, 49 Geräte inkl. Räume
- Matter-Lampen (~70): einzeln koppeln, auf dem Mini-PC nachholen
- Nuki: bewusst weggelassen
- Anzeige: bisher Chrome `--app` (nicht `--kiosk`), Seitenleiste eingeklappt
- Design: dunkles Theme, transparente Kacheln via card-mod
- Umzug: komplettes HA-Backup (.tar) wiederherstellen

## Wichtig: Home Assistant OS hat keinen Browser am HDMI-Ausgang
HAOS zeigt am Monitor nur eine Text-Konsole – Chrome/Kiosk läuft dort nicht
einfach so. Möglichkeiten für Punkt 7:
1. **Add-on „HAOSKiosk“** (Community-Add-on): zeigt ein Dashboard direkt am
   HDMI-Ausgang des Mini-PCs, mit Touch. Einfachste Lösung, kein Zusatzgerät.
2. Zweites kleines Gerät am Monitor (z. B. Raspberry Pi oder altes Notebook)
   mit Browser im Kiosk-Modus, das auf `http://homeassistant.local:8123` zeigt.
3. Mini-PC mit Proxmox: HA als VM + kleines Linux mit Kiosk-Browser.

## Stand 27.09.2026 abends
Erledigt:
- Mini-PC (192.168.0.191) mit HAOS, Backup wiederhergestellt, Git pull aktiv (Repo öffentlich)
- 28.10.2026 Umzug auf Lenovo ThinkCentre M720q (i5-9500T, 512-GB-NVMe): HAOS 18.4 per Ubuntu-Live-Stick + „Laufwerke“ aufgespielt, Secure Boot aus, Backup „Umzug“ wiederhergestellt, feste IP 192.168.0.191 (Gateway/DNS 192.168.0.1). Alter Shuttle aus – nicht mehr mit HAOS ans Netz (doppelte IP/Bot); später als Küchenanzeige neu aufsetzen.
- Touchmonitor über „HAOS Kiosk Display“, Dashboard „Flur“ (`/flur-display/start`) im Apple-Stil, Deutsch
- Startseite: Termine heute/morgen/übermorgen, Ferienwohnung (Holidu) & Stellplätze (Portal),
  Einkaufsliste (nur offene), Schnellzugriff (Hoftor, Lichter, Einkauf, Kameras, Amazon, Stellplätze verwalten)
- Seiten: Einkauf (Schnell hinzufügen), Kalender, Licht (49 Lampen), Kameras, Klingel (Unterseite)
- Kalender „Geburtstage“ heißt „Termine“ (calendar.geburtstage)
- Telegram-Bot „Zuhause“ (Marco + Frau freigegeben): Claude, Termine eintragen, „Liste“, „Monitor“
- Ring-Klingel (Hoftor): beim Klingeln Kamera-Seite auf dem Monitor + Foto per Telegram
- Tapo-Kameras (Generische Kamera, RTSP stream2): Hof-Tor, Giebel vorne, Giebel hinten, Hof hinten – live

- Musik: Music Assistant + Apple Music, Seite „Musik“ (Räume, Favoriten, Musik hierher), Einkaufsliste per Telegram
- Kalender: Ferienwohnung = Holidu + Portal (export-ical-ferienwohnung.php, gleicher Anreisetag), Rest = Stellplätze
- Design umschaltbar Hell/Dunkel/Automatisch, Nachtmodus Monitor (Test: ab 21:15, später 22:30), Tastatur-Varianten A/B/C

Telegram-Bot kann Termine jetzt auch **ändern und löschen** (claude_tools/kalender.py,
bearbeitet die Kalenderdatei direkt; vor jeder Änderung Sicherheitskopie nach
/media/kalender_sicherung, die letzten 50 bleiben). Serientermine werden nicht angefasst.

Aufgaben: Liste todo.aufgaben (Lokale To-do-Liste „Aufgaben“, einmalig in der Oberfläche
angelegt), auf der Startseite + eigene Seite „Aufgaben“ mit Schnell-Knöpfen; Telegram: „Aufgaben“.

Kameras live: App go2rtc (a889bffc_go2rtc) wandelt die Tapo-Streams in MJPEG um, das kann der
Kiosk-Browser. /config/go2rtc.yaml (lokal, mit Passwörtern) erzeugt claude_tools/go2rtc_einrichten.py
beim HA-Start aus den Generic-Camera-Einträgen. Dashboard lädt http://localhost:1984/api/stream.mjpeg?src=<entity>
(nur auf dem Monitor), Großansicht <entity>_hd (stream1). go2rtc-API von außen nur mit Passwort.

Grundriss (v3): Haupthaus fest nach Bauplan (Maßketten, Meter; Türen/Fenster/Treppe), Zusatzflächen
frei; alte Kästchen-Anordnung wird beim Laden per Raumnamen übertragen. Eigene Vollbild-Seite www/grundriss.html (iframe im Dashboard, liest hass aus dem
Eltern-Fenster). Bearbeiten-Modus: Wände ziehen (gemeinsame Wände wandern mit), Räume verschieben,
Lampen platzieren, Name/Symbol wählen, Foto-Vorlage /local/grundriss.jpg. Gespeichert über
script.grundriss_speichern → /config/www/grundriss_daten.json (lokal). Neue Lampen landen automatisch im Raum.

Offen / morgen prüfen:
- [ ] Kameras live auf dem Monitor? Flüssig? Mini-PC-Modell erfragen (Transcoding-Last)
- [ ] Ring live über Ring-MQTT → go2rtc; Tapo schwenken über HACS „Tapo: Cameras Control“
- [ ] Liste „Aufgaben“ in HA anlegen (Lokale To-do-Liste) – macht Marco
- [ ] Termin ändern/löschen per Telegram in den ersten Tagen beobachten
- [ ] Nachtmodus (22:30–6:30) prüfen; tagsüber alle 5 Min. Abschaltung aus
- [ ] Design-Entscheidung (Hell/Dunkel/Automatisch), Tastatur-Variante wählen
- [ ] Music-Assistant-Gruppe „Ganzes Haus“ + Knopf „Favoriten überall“; Name der Favoriten-Playlist prüfen
- [ ] Ring echtes Live-Bild auf dem Monitor (Ring-MQTT), falls gewünscht
- [ ] Matter-Lampen, restliche Shellys, Nachtabschaltung Display, Grundriss
- [ ] Feste IP im Omada Controller, alten Docker-HA auf dem Laptop stoppen, Updates einspielen

## Stand laut Backup vom 27.09.2026 (HA 2026.8.3)
- 14 Räume, 49 IKEA-Lampen (Dirigera), 1 Shelly (Hoftor), 3 Kalender,
  Einkaufsliste, Met.no, HomeKit-Bridge, HACS mit Dirigera-Integration
- Noch **nicht** drin: card-mod, Matter, weitere Shellys, Automationen
- `light.flur` hat keinen Raum zugeordnet
- Grundriss-Vorlage: Architektenplan als `/local/grundriss.jpg` (1024×768)

## Dateien
Siehe `README.md`. Backups (.tar) gehören **nicht** hierher (enthalten Passwörter/Tokens).

## Jarvis-Werkzeuge (packages/jarvis.yaml)
Gemeinsam für Sprachassistent und Telegram-Bot (beide nutzen den Claude-Gesprächsagenten):
Kamerabild per Telegram, Belegung FW/Stellplätze (ohne Namen), Nachricht auf den Monitor,
Erinnerungen (⏰-Aufgabe mit Uhrzeit, jede Minute geprüft). Dazu 07:00 Morgen-Übersicht und
22:30 Abend-Check Licht mit Knöpfen (abschaltbar über input_boolean.*_pause).
Skripte müssen in Sprachassistenten → Entitäten freigeben für Assist freigegeben werden.

## Stand 31.10.2026: Küche, Haus-Wächter, Müll, Morgen-Nachricht
- Der Touchmonitor hängt jetzt in der **Küche** (wird dort am meisten genutzt). Für den Flur kommt ein zweiter
  Monitor an den alten Shuttle-PC (schlankes Linux + Kiosk-Browser, **nicht** HAOS); Vorschlag iiyama ProLite T2252MSC-B2.
- **Küche** (`packages/kueche.yaml`, `claude_tools/kueche.py`, `www/kueche.html`, Reiter „Küche“): Essensplan wie eine
  Planer-App. Einrichten (Personen, Kochtage, Budget, Stil, Reste, Ernährung, Allergien, Zeit, Geräte, Arbeitszeiten),
  Claude plant passend zu Familienkalender, Mathildas Stundenplan (`mucki_daten.json`), Vorrat/Ernte und Garten.
  Kochmodus mit Timern (Ansage Küchen-HomePod), Rezepte aus Link/Text/Foto, Einkauf → `todo.einkaufsliste`.
  Freitag 16:30 automatisch Plan für die nächste Woche (abschaltbar: `input_boolean.kueche_auto_pause`).
  Telegram: „Was gibt's heute zu essen?“, „Lasagne am Samstag“, „Plan nächste Woche“, „Ernte: …“, Rezept-Link,
  Foto mit Text „Rezept“. Daten lokal in `/config/www/kueche_daten.json`.
- **Haus-Wächter** (`packages/haus_waechter.yaml`): Batterien (≤ 20 % oder stumm) → Telegram + Monitor,
  Wasser-Alarm (Conel/SafeFloor-Leckage, Wassermelder), Dauerfluss, Rauchmelder, Waschmaschine/Trockner/Spülmaschine
  fertig (Shelly Plug S mit diesem Namen), Sonnenstrom-Tipp, Urlaubsmodus. Kennungen (Viessmann/Conel/Melder) findet
  `claude_tools/haus_kennungen.py`. Keine automatische Wasser-Absperrung.
- **Müll** (`packages/muell.yaml`): GIB-Abfall-App → Kalender-Link an den Bot („Müll-Link: …“) oder .ics-Datei.
- **Morgen-Nachricht** (`packages/tagesbrief.yaml`): Mo–Fr 6:40, Sa/So 8:10 an alle per Telegram.
- Hinweise oben auf der Startseite: `sensor.haus_hinweise`.

## Stand 31.10.2026 (später): Alltagshelfer, Kochmodus, Ausflugsplaner, Hausstil
- **Alltag** (`packages/alltag.yaml`, `claude_tools/alltag.py`): Schultasche am Vorabend (aus `mucki_daten.json`), Schulferien
  Niedersachsen (ferien-api.de) im Kalender, Wochenvorschau sonntags 18 Uhr, Geburtstage 7 Tage/1 Tag vorher mit Geschenkideen,
  Stamm-Einkauf (`input_text.einkauf_stamm`, freitags 14 Uhr), DWD-Unwetter Wesermarsch mit Tipps, „Alle aus dem Haus“-Check
  (person-Entitäten), Warmwasser mit Sonnenstrom (ViCare-Knopf „einmalige Warmwasserbereitung“), Ausweise/Pässe
  (`/config/dokumente.json`), Hausarbeit der Woche (`/config/hausarbeit.json`, wird beim ersten Lauf angelegt – dort anpassen).
- **Kochmodus**: gezeichnete Comic-Szenen je Arbeitsschritt, Fotos der Gerichte (Rezeptseite per Websuche → og:image).
- **Ausflugsplaner** (`packages/ausflug.yaml`, `claude_tools/ausflug.py`, `www/ausflug.html`, Reiter „Ausflug“): Claude mit
  Websuche, Route als Google-Maps-Link ab Zone „Zuhause“, Telegram „Ausflug …“.
- **Hausstil** (`www/hausstil.css`, `themes/apple.yaml`): Farben/Schrift wie das Handbuch „Zuhause“.
- Einkaufsliste (`todo.einkaufsliste`) ist die Einkaufsliste-Integration: **kein** Beschreibungsfeld bei `todo.add_item`.

## Automatische Updates (31.10.2026)
- `packages/updates.yaml`: nachts 03:40 Add-ons/HACS (Update seit ≥ 2 Tagen da), Core ab x.y.1 (oder nach 14 Tagen) mit
  Sicherung, OS nach 7 Tagen (nicht in derselben Nacht wie Core). Keine Geräte-Firmware. Nicht im Urlaubsmodus.
  Pause: `input_boolean.updates_pause`. Telegram an Marco vorher und nach dem Core-Neustart.
