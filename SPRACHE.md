# Sprachsteuerung für Home Assistant

Ziel: „Mach im Wohnzimmer das Licht aus“, „Trag Zahnarzt Mucki am Dienstag um
10 Uhr ein“, „Setz Milch auf die Einkaufsliste“, „Was steht diese Woche an?“

## 1. Kalender
Neue Termine landen im vorhandenen lokalen Kalender „Geburtstage“
(`calendar.geburtstage`) – der dient als Familienkalender.
(Holidu und die Website sind Abo-Kalender – die kann man nur lesen, nicht beschreiben.)

## 2. Claude als Gesprächspartner einbinden
1. Einstellungen → Geräte & Dienste → Integration hinzufügen → **Anthropic**
   → API-Schlüssel eintragen (am besten einen eigenen Schlüssel in der Claude
   Console anlegen, nicht den vom Sprachnotiz-Tool).
2. In den Optionen der Integration **„Home Assistant steuern“ (Assist)** aktivieren.
3. Einstellungen → Sprachassistenten → Assistent bearbeiten:
   - Sprache: Deutsch
   - Gesprächsagent: Claude
   - „Befehle bevorzugt lokal verarbeiten“: **an** (einfache Licht-Befehle
     laufen dann blitzschnell ohne KI)

## 3. Was darf die Sprache steuern?
Einstellungen → Sprachassistenten → Reiter **Entitäten freigeben**:
- alle Lichter ✅
- `calendar.holidu`, `calendar.privat_mit_buchung`, `calendar.geburtstage` ✅ (zum Vorlesen)
- `todo.einkaufsliste` ✅
- Skript „Termin eintragen“ ✅ (kommt automatisch aus `packages/termine.yaml`)
- Jarvis-Werkzeuge aus `packages/jarvis.yaml` ✅ – gelten für Sprache UND Telegram-Bot:
  „Jarvis Tagesüberblick“, „Jarvis Kamerabild schicken“, „Jarvis Belegung Ferienwohnung und Stellplätze“ (nur Zeiträume,
  keine Gästenamen), „Jarvis Nachricht auf den Flur-Monitor“, „Jarvis Erinnerung“
- `todo.aufgaben` ✅
- Hoftor: bewusst **nicht** freigeben, solange niemand per Sprache das Tor öffnen soll

## 4. Spracherkennung und Sprachausgabe
Eine von zwei Varianten:
- **Home Assistant Cloud (Nabu Casa)**, ca. 7,50 €/Monat: beste deutsche
  Erkennung, bringt nebenbei sicheren Fernzugriff mit.
- **Kostenlos lokal**: Add-ons „Whisper“ (Erkennung) + „Piper“ (Stimme).
  Hängt von der Leistung des Mini-PCs ab.

## 5. Womit spricht man?
- **Handy**: Home-Assistant-App → Assist-Knopf. Auf dem iPhone per Kurzbefehl
  auch mit „Hey Siri, Assist“.
- **Am Monitor im Flur**: „Home Assistant Voice“ (kleiner Lautsprecher mit
  Mikrofon, Aktivierungswort „Okay Nabu“) neben den Monitor stellen. Das Mikrofon
  im Browser des Monitors funktioniert nur über eine HTTPS-Adresse.

## Beispielsätze
- „Mach im Wohnzimmer das Licht an.“ / „Schalte alle Lichter draußen aus.“
- „Trag nächsten Dienstag um 10 Uhr Zahnarzt Mucki ein.“
- „Geburtstag Oma am 14. November eintragen.“
- „Was steht diese Woche im Kalender?“ / „Welche Buchungen kommen im Oktober?“
- „Setz Milch und Eier auf die Einkaufsliste.“

---

# Termine per Telegram (privat, getrennt von der Firma)

Ein eigener Telegram-Bot, der nur dir (und freigegebenen Personen) antwortet.
Die Automation dazu liegt in `packages/telegram.yaml`.

## 1. Bot anlegen (Telegram-App, 2 Minuten)
1. In Telegram den Chat **@BotFather** öffnen → `/newbot` schicken.
2. Namen eingeben, z. B. `Zuhause`.
3. Benutzernamen eingeben, muss auf `bot` enden, z. B. `urlaub_zuhause_bot`.
4. BotFather schickt einen **Token** (`123456789:ABC…`) → kopieren, nicht weitergeben.
5. Deine Chat-ID herausfinden: Chat **@userinfobot** öffnen → `/start` → er
   antwortet mit deiner **Id** (eine Zahl).

## 2. In Home Assistant einbinden
1. Einstellungen → Geräte & Dienste → Integration hinzufügen → **Telegram bot**.
2. Plattform: **Polling** (kein Zugriff aus dem Internet nötig).
3. API-Token vom BotFather einfügen → weiter.
4. Bei der Integration **„Erlaubte Chat-ID hinzufügen“** → deine Id von @userinfobot.
5. In Telegram deinem neuen Bot einmal `/start` schreiben.

## 3. Claude als Gesprächsagent
1. Integration hinzufügen → **Anthropic** → API-Schlüssel.
2. Beim Gesprächsagenten: **„Home Assistant steuern“ / Assist** aktivieren.
   Anweisungen (Prompt) z. B.:
   `Du bist der Assistent der Familie. Antworte kurz und auf Deutsch. Termine trägst du mit dem Skript "Termin eintragen" ein und bestätigst Datum und Uhrzeit.`
3. Einstellungen → Sprachassistenten → **Entitäten freigeben**: Kalender,
   Einkaufsliste, Skript „Termin eintragen“, gewünschte Lichter.

Sprachnachrichten: einfach die Diktierfunktion der Handy-Tastatur (Mikrofon) nutzen –
der Bot bekommt dann Text.
