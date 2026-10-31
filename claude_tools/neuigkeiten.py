#!/usr/bin/env python3
"""Einmalige Übersicht der Neuerungen vom 31.10.2026 (2. Fassung mit den Ergänzungen vom selben Tag) per Telegram an Mirka (Wunsch Marco), danach eine kurze Bestätigung an Marco.
Wird von packages/neuigkeiten.yaml nach dem Start aufgerufen; die Markierungsdatei sorgt dafür, dass es nur einmal passiert.
Aufruf: neuigkeiten.py <base64-JSON {chats: [...]}>"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import akte  # noqa: E402 – Telegram senden, Empfänger nach Vorname finden

MARKE = "/config/.neuigkeiten_2026_10_31_b"   # zweite, ergänzte Fassung (Wunsch Marco)

TEXTE = [
    """Hallo Mirka 👋 Hier nochmal die komplette Übersicht aller Neuerungen im Haus – mit allem, was heute noch dazugekommen ist. Der große Monitor hängt jetzt in der Küche.

🍽 KÜCHE (Reiter „Küche“ am Monitor)
• Essensplan für die Woche: Claude plant die Abendessen passend zu unseren Terminen, deinen Arbeitszeiten, Mathildas Stundenplan, Vorrat, Gartenernte und Sonderangeboten im Laden. Freitags um 16:30 kommt der Plan für die nächste Woche automatisch.
• Tage tauschen, ändern, „Essen gehen“ eintragen oder Lieblingsgerichte merken.
• Kochen: Schritt für Schritt am Monitor mit kleinen Zeichnungen, Fotos der Gerichte und Timern.
• Einkaufsliste: alle Zutaten der Woche mit Preisen und Budget; Laden spontan wechseln (z. B. doch Netto) und prüfen, ob es dort alles gibt.
• Rezepte: Link, Text oder Foto aus dem Kochbuch → sauberes Rezept.
• Per Telegram: „Was gibt's heute zu essen?“, „Samstag gehen wir essen“, „Ernte: 3 Kürbisse“, Foto mit Text „Rezept“.

🛒 EINKAUF
• „Schick mir die Einkaufsliste“ (oder „schick Mirka die Einkaufsliste“) an den Bot – kommt sofort. Am Monitor gibt es dafür auch einen Knopf.
• Stamm-Einkauf: was jede Woche gebraucht wird, kommt freitags um 14 Uhr automatisch auf die Liste.""",

    """📆 ALLTAG & KALENDER
• Jeden Morgen eine kurze Nachricht: Termine, Wetter, Müll, Essen, Fälliges. Sonntags 18 Uhr die Wochenvorschau.
• NEU: Regelmäßige Termine per Telegram, z. B. „Mathilda Turnen jeden Donnerstag 16 Uhr“ oder nachträglich „der Termin ist jeden Dienstag“. Umbenennen geht auch („… soll nur Marco singen heißen“).
• Am Vorabend: was Mathilda in die Schultasche braucht. Schulferien stehen automatisch im Kalender.
• Geburtstage: eine Woche vorher mit Geschenkideen, am Vortag nochmal.
• Hausarbeit: montags kommen die Aufgaben der Woche in die Aufgabenliste, abwechselnd verteilt.
• Müll (GIB): Erinnerung am Vorabend um 18:30, steht auch auf dem Monitor.
• Ausweise & Pässe: „Reisepass Mathilda läuft am … ab“ an den Bot – er erinnert rechtzeitig.

🏠 HAUS
• Wasser-Alarm (Conel/Bodensensor) und Rauchmelder melden sich sofort per Telegram und Durchsage.
• NEU: „Wasser läuft ohne Pause“ meldet sich nur noch, wenn die Wasseruhr wirklich eine Stunde lang durchläuft – keine falschen Meldungen mehr.
• Schwache Batterien in Sensoren meldet das Haus von selbst.
• Waschmaschine, Trockner, Spülmaschine sagen „fertig“, sobald die Steckdosen eingerichtet sind.
• Unwetterwarnungen für die Wesermarsch mit Tipps. Viel Sonnenstrom übrig → Tipp, jetzt Waschmaschine & Co. zu starten.
• Urlaubsmodus (Knopf am Monitor): Licht wie bewohnt, strengerer Wasser-Wächter.
• NEU: Updates laufen jetzt nachts von selbst, vorsichtig und mit Sicherung.
• NEU: Unser Standort ist jetzt richtig eingestellt – Wetter, Sonnenzeiten und Routen stimmen.""",

    """🚲 AUSFLUG (Reiter „Ausflug“)
• Rad, Auto, zu Fuß oder Bahn wählen, was wir mögen (Natur, Spa, Therme, Nordsee, Tiere, Café …) – Claude sucht passende Ziele mit Öffnungszeiten, Preisen, Bildern, Ablauf und Route ab Haustür für Google Maps.
• NEU: Auch „Wochenende mit Übernachtung“ mit Unterkunft und Zwei-Tages-Plan – mit dem Auto z. B. „bis 3 Stunden“ Fahrt.
• NEU: Claude schaut auch auf Komoot und anderen Tourenportalen nach fertigen Rad- und Wandertouren (Knopf „Komoot“), auf Wellness-Plattformen und Bewertungen – und sucht immer mindestens einen echten Geheimtipp (Hofcafés, Blogs, Lokalzeitung).
• „Aufs Handy“ schickt den Plan per Telegram. Oder einfach an den Bot: „Was können wir am Wochenende unternehmen?“

🎨 Alles sieht einheitlich aus – in unseren Farben mit Wappen.

Fragen? Einfach hier dem Bot schreiben 🙂""",
]


def main():
    if os.path.exists(MARKE):
        print(json.dumps({"ok": True, "schon": True}))
        return
    chats = [str(c) for c in json.loads(base64.b64decode(sys.argv[1]).decode("utf-8")).get("chats") or []]
    mirka, name = None, None
    for n in ("Mirka", "Mika", "Mirk"):
        mirka, name = akte.empfaenger_finden(n, chats)
        if mirka:
            break
    if not mirka:
        print(json.dumps({"ok": False, "fehler": "Mirka finde ich nicht unter den Telegram-Empfängern (bekannt: "
                                                  + akte.bekannte_namen(chats) + f", {len(chats)} Chats)"}, ensure_ascii=False))
        return
    for t in TEXTE:
        akte.senden(mirka, t)
    with open(MARKE, "w") as f:
        f.write("gesendet")
    marco = next((c for c in chats if c != mirka), None)
    if marco:
        akte.senden(marco, f"✅ {name or 'Mirka'} hat die ergänzte Übersicht aller Neuerungen per Telegram bekommen.")
    print(json.dumps({"ok": True, "an": name}))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": f"{type(fehler).__name__}: {fehler}"[:200]}))
