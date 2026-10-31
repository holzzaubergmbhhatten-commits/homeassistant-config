#!/usr/bin/env python3
"""Einmalige Übersicht der Neuerungen vom 31.10.2026 per Telegram an Mirka (Wunsch Marco), danach eine kurze Bestätigung an Marco.
Wird von packages/neuigkeiten.yaml nach dem Start aufgerufen; die Markierungsdatei sorgt dafür, dass es nur einmal passiert.
Aufruf: neuigkeiten.py <base64-JSON {chats: [...]}>"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import akte  # noqa: E402 – Telegram senden, Empfänger nach Vorname finden

MARKE = "/config/.neuigkeiten_2026_10_31"

TEXTE = [
    """Hallo Mirka 👋 Marco hat mich gebeten, dir alle Neuerungen im Haus zusammenzufassen. Der große Monitor hängt jetzt in der Küche.

🍽 KÜCHE (Reiter „Küche“ am Monitor)
• Essensplan für die Woche: Claude plant die Abendessen passend zu unseren Terminen, deinen Arbeitszeiten, Mathildas Stundenplan, Vorrat, Gartenernte und Sonderangeboten im Laden. Freitags um 16:30 kommt der Plan für die nächste Woche automatisch.
• Tage tauschen, ändern, „Essen gehen“ eintragen oder Lieblingsgerichte merken.
• Kochen: Schritt für Schritt am Monitor mit kleinen Zeichnungen, Fotos der Gerichte und Timern (der Küchen-HomePod sagt Bescheid).
• Einkaufsliste: alle Zutaten der Woche zusammengerechnet, mit Preisen; Laden spontan wechseln und prüfen, ob es alles dort gibt.
• Rezepte: Link, Text oder Foto aus dem Kochbuch → sauberes Rezept.
• Per Telegram: „Was gibt's heute zu essen?“, „Samstag gehen wir essen“, „Ernte: 3 Kürbisse“, Foto mit Text „Rezept“.

🛒 EINKAUF
• Die Einkaufsliste kommt bei jeder Änderung per Telegram. „Schick mir die Einkaufsliste“ an den Bot geht jederzeit.
• Stamm-Einkauf: was jede Woche gebraucht wird, kommt freitags um 14 Uhr automatisch auf die Liste (Reiter „Einkauf“).""",

    """📆 ALLTAG
• Jeden Morgen eine kurze Nachricht: Termine, Wetter, Müll, Essen, Fälliges.
• Sonntags 18 Uhr: Wochenvorschau.
• Am Vorabend: was Mathilda in die Schultasche braucht (z. B. Schwimmsachen). Schulferien stehen automatisch im Kalender.
• Geburtstage: eine Woche vorher mit Geschenkideen, am Vortag nochmal.
• Hausarbeit: montags kommen die Aufgaben der Woche in die Aufgabenliste, abwechselnd verteilt.
• Müll: Erinnerung am Vorabend um 18:30 („Biotonne rausstellen“), am Monitor steht es auch.
• Ausweise & Pässe: „Reisepass Mathilda läuft am … ab“ an den Bot – er erinnert rechtzeitig.

🏠 HAUS
• Wasser-Alarm (Conel/Bodensensor) und Rauchmelder melden sich sofort per Telegram und Durchsage.
• Schwache Batterien in Sensoren meldet das Haus von selbst.
• Waschmaschine, Trockner, Spülmaschine sagen „fertig“, sobald die Steckdosen eingerichtet sind.
• Unwetterwarnungen für die Wesermarsch mit Tipps (z. B. Gartenmöbel sichern).
• Viel Sonnenstrom übrig → Tipp, jetzt Waschmaschine & Co. zu starten.
• Urlaubsmodus (Knopf am Monitor): Licht wie bewohnt, strengerer Wasser-Wächter.

🚲 AUSFLUG (Reiter „Ausflug“)
• Rad, Auto, zu Fuß oder Bahn auswählen, was wir mögen (Natur, Spa, Therme, Nordsee, Tiere …) – Claude sucht passende Ziele mit Öffnungszeiten, Preisen, Bildern, Ablauf und Route für Google Maps. „Aufs Handy“ schickt den Plan per Telegram.
• Oder einfach an den Bot: „Was können wir am Wochenende unternehmen?“

🎨 Alles sieht jetzt einheitlich aus – in unseren Farben mit Wappen.

Fragen? Einfach hier dem Bot schreiben 🙂""",
]


def main():
    if os.path.exists(MARKE):
        print(json.dumps({"ok": True, "schon": True}))
        return
    chats = [str(c) for c in json.loads(base64.b64decode(sys.argv[1]).decode("utf-8")).get("chats") or []]
    mirka, name = akte.empfaenger_finden("Mirka", chats)
    if not mirka:
        print(json.dumps({"ok": False, "fehler": "Mirka nicht unter den Telegram-Empfängern gefunden"}))
        return
    for t in TEXTE:
        akte.senden(mirka, t)
    with open(MARKE, "w") as f:
        f.write("gesendet")
    marco = next((c for c in chats if c != mirka), None)
    if marco:
        akte.senden(marco, f"✅ {name or 'Mirka'} hat die Übersicht aller Neuerungen per Telegram bekommen.")
    print(json.dumps({"ok": True, "an": name}))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": f"{type(fehler).__name__}: {fehler}"[:200]}))
