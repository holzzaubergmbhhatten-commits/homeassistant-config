#!/usr/bin/env python3
"""Fotos per Telegram (z. B. von Marcos Frau): Claude erkennt, was drauf ist, und ordnet es zu.

Aufruf aus der Automation "Telegram-Foto" (packages/eingang.yaml):
  foto_eingang.py neu <base64-JSON {datei, text, von, wetter}>
      Pflanze/Beet  → Antwort {"art": "garten"}; die Automation macht dann den Garten-Fotocheck (garten_ki.py)
      Haus & Hof    → Infos herauslesen, Zuordnung vorschlagen (z. B. "Geräte → Trockner"), im Eingang ablegen
  foto_eingang.py liste -          alle Einträge (für die Eingang-Seite)
  foto_eingang.py erledigt <id>    als übernommen markieren
  foto_eingang.py offen <id>       wieder offen
  foto_eingang.py loeschen <id>    Eintrag und Foto löschen
Fotos liegen in /media/eingang (nur mit Home-Assistant-Anmeldung sichtbar), die Liste in /config/eingang.json.
Ausgabe immer JSON.
"""
import base64
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import garten_ki  # noqa: E402  – Schlüssel, Modell, Foto verkleinern

LISTE = "/config/eingang.json"
ORDNER = "/media/eingang/"

ERKENNEN = """Du hilfst einer Familie auf einem Resthof in Norddeutschland, ihr Haus-Handbuch zu pflegen. Jemand hat ein Foto per
Telegram geschickt, manchmal mit einer kurzen Erklärung. Entscheide, worum es geht, und lies alle nützlichen Infos heraus.
Bereiche im Handbuch: Haustechnik (Heizung, Wärmepumpe, Solar, Wasser, Abwasser), Sicherungen (Verteiler, Sicherungskästen,
Beschriftungen), Geräte (Haushaltsgeräte), Maschinen (Garten- und Werkstattmaschinen, Fahrzeuge wie die Ape, Betriebsstoffe),
Netzwerk (Router, WLAN, Kameras), Wohnwagen, Wo ist was (Absperrhähne, Schalter, Standorte), Wartung, Sonstiges.
Antworte NUR mit einem JSON-Objekt:
{"art": "garten" (lebende Pflanze, Beet, Gemüse, Schädling) oder "haus" (alles andere),
 "titel": "kurzer Titel, z. B. Typenschild Trockner",
 "bereich": "einer der Bereiche oben",
 "zuordnung": "wohin genau, z. B. Geräte → Trockner Haier",
 "erkannt": "alle lesbaren Fakten als kurze Zeilen (Hersteller, Modell, Typ, Leistung, Maße, Sicherung, Standort …)",
 "fragen": "was unklar ist oder nachgefragt werden sollte, sonst leer",
 "antwort": "kurze freundliche Antwort für den Chat (2–4 Sätze): was du erkannt hast und wo es hinkommt; bei Unklarem nachfragen"}
Seriennummern, Zählerstände, Zugangsdaten und Codes nur in "erkannt" erwähnen, nie in "antwort"."""


def laden():
    try:
        with open(LISTE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def speichern(liste):
    tmp = LISTE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LISTE)


def erkennen(auftrag, bild):
    import anthropic
    inhalt = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": bild}},
              {"type": "text", "text": f"Von: {auftrag.get('von', '')}\nText dazu: {auftrag.get('text', '') or '(keiner)'}"}]
    client = anthropic.Anthropic(api_key=garten_ki.api_schluessel(), timeout=40, max_retries=1)
    a = client.messages.create(model=garten_ki.MODELL, max_tokens=1500, system=ERKENNEN,
                               messages=[{"role": "user", "content": inhalt}],
                               extra_body={"output_config": {"effort": "low"}, "fallbacks": "default"},
                               extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"})
    roh = "".join(b.text for b in a.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", roh, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {"art": "haus", "titel": "Foto", "erkannt": roh[:1500], "antwort": "Danke, ich habe das Foto abgelegt."}


def neu(auftrag):
    datei = auftrag.get("datei", "")
    if not os.path.realpath(datei).startswith(ORDNER) or not os.path.exists(datei):
        return {"ok": False, "fehler": "Foto nicht gefunden"}
    bild = garten_ki.foto_laden(datei)
    e = erkennen(auftrag, bild)
    # Garten: dann macht die Automation den bekannten Fotocheck (eigener Aufruf, eigene Zeit)
    if e.get("art") == "garten":
        return {"ok": True, "art": "garten"}
    liste = laden()
    eintrag = {"id": datetime.now().strftime("%Y%m%d%H%M%S"), "datei": os.path.basename(datei),
               "datum": datetime.now().strftime("%d.%m.%Y %H:%M"), "von": auftrag.get("von", ""), "text": auftrag.get("text", ""),
               "titel": e.get("titel", "Foto"), "bereich": e.get("bereich", "Sonstiges"), "zuordnung": e.get("zuordnung", ""),
               "erkannt": e.get("erkannt", ""), "fragen": e.get("fragen", ""), "status": "neu"}
    liste.append(eintrag)
    speichern(liste[-300:])
    antwort = e.get("antwort") or f"Danke! Abgelegt unter {eintrag['zuordnung'] or eintrag['bereich']}."
    return {"ok": True, "art": "haus", "text": antwort + "\n📥 Liegt jetzt im Eingang (Home Assistant → Eingang)."}


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else "liste"
    wert = sys.argv[2] if len(sys.argv) > 2 else ""
    if aktion == "neu":
        print(json.dumps(neu(json.loads(base64.b64decode(wert).decode("utf-8"))), ensure_ascii=False))
        return
    liste = laden()
    if aktion in ("erledigt", "offen", "loeschen"):
        for e in liste:
            if e.get("id") == wert:
                if aktion == "loeschen":
                    try:
                        os.remove(os.path.join(ORDNER, os.path.basename(e.get("datei", ""))))
                    except OSError:
                        pass
                    liste.remove(e)
                else:
                    e["status"] = "erledigt" if aktion == "erledigt" else "neu"
                break
        speichern(liste)
    print(json.dumps({"ok": True, "eintraege": list(reversed(liste))}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": f"{type(fehler).__name__}: {fehler}"[:300], "eintraege": []}, ensure_ascii=False))
