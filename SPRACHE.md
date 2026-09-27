# Sprachsteuerung für Home Assistant

Ziel: „Mach im Wohnzimmer das Licht aus“, „Trag Zahnarzt Mucki am Dienstag um
10 Uhr ein“, „Setz Milch auf die Einkaufsliste“, „Was steht diese Woche an?“

## 1. Kalender „Termine“ anlegen
Einstellungen → Geräte & Dienste → Integration hinzufügen → **Lokaler Kalender**
→ Name: `Termine` → ergibt `calendar.termine`.
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
- `calendar.termine`, `calendar.holidu`, `calendar.privat_mit_buchung`, `calendar.geburtstage` ✅ (zum Vorlesen)
- `todo.einkaufsliste` ✅
- Skript „Termin eintragen“ ✅ (kommt automatisch aus `packages/termine.yaml`)
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
