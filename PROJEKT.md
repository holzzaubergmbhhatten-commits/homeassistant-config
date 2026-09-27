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

## Offene Punkte
0. [ ] Git-pull einrichten (README Schritt 2–3), danach Kiosk-Dashboard auf `flur-display` umstellen
- [ ] Feste IP 192.168.0.191 im Omada Controller reservieren
- [ ] Alten Home Assistant im Docker auf dem Laptop stoppen
- [ ] 3 Updates (Core 2026.9.4, OS 18.3, Shelly) einspielen
1. [x] Backup auf dem Mini-PC wiederhergestellt
2. [ ] Restliche Shelly-Geräte (Garagenlicht, Wegbeleuchtung)
3. [ ] Matter-Lampen auf dem Mini-PC koppeln
4. [ ] HACS + card-mod neu einrichten (prüfen, ob aus Backup schon da)
5. [ ] Geburtstage in den Kalender
6. [ ] Grundriss: genaue, editierbare Grafik
7. [x] Touchmonitor am Mini-PC, App „HAOS Kiosk Display“ zeigt `flur-monitor` (27.09.2026)
8. [ ] Bildschirmtastatur prüfen
9. [ ] Nachtabschaltung des Displays (Uhrzeit / Sprachbefehl)
10. [ ] Wisch-Navigation zwischen Dashboard-Seiten (HACS: „Swipe Navigation“)

11. [ ] Sprachsteuerung einrichten (siehe `sprache/ANLEITUNG.md`)

## Stand laut Backup vom 27.09.2026 (HA 2026.8.3)
- 14 Räume, 49 IKEA-Lampen (Dirigera), 1 Shelly (Hoftor), 3 Kalender,
  Einkaufsliste, Met.no, HomeKit-Bridge, HACS mit Dirigera-Integration
- Noch **nicht** drin: card-mod, Matter, weitere Shellys, Automationen
- `light.flur` hat keinen Raum zugeordnet
- Grundriss-Vorlage: Architektenplan als `/local/grundriss.jpg` (1024×768)

## Dateien
Siehe `README.md`. Backups (.tar) gehören **nicht** hierher (enthalten Passwörter/Tokens).
