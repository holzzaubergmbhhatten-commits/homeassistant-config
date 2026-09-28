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

Grundriss: eigene Vollbild-Seite www/grundriss.html (iframe im Dashboard, liest hass aus dem
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
