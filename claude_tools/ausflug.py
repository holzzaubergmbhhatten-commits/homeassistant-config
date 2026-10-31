#!/usr/bin/env python3
"""Ausflugsplaner (packages/ausflug.yaml, www/ausflug.html): Claude sucht Ausflugsziele – mit dem Rad, dem Auto, zu Fuß oder
mit der Bahn, in der Nähe oder weiter weg – passend zu Wetter, Zeit, Wünschen und Familie, mit Bildern, Ablauf und Route.

Aufrufe:
  ausflug.py speichern <base64-Stücke>   Daten der Seite speichern (gemerkt, erlebt, Vorlieben)
  ausflug.py ki <base64-JSON {art: "ideen", wie, wann, dauer, wer, interessen, weite, wunsch, wetter, heim: {lat, lon}, chat}>
      läuft im Hintergrund (Websuche dauert), Fortschritt in ausflug_status.json, Ergebnis in ausflug_daten.json → "ideen".
Daten lokal: /config/www/ausflug_daten.json (nicht im Repository). Die Heimadresse kommt aus Home Assistant (Zone Zuhause),
sie steht nicht im Code.
"""
import base64
import json
import os
import re
import sys
import time
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATEN = "/config/www/ausflug_daten.json"
STATUS = "/config/www/ausflug_status.json"

SYSTEM = """Du bist ein ortskundiger Ausflugsplaner für eine Familie aus Ovelgönne in der Wesermarsch (Niedersachsen, zwischen
Oldenburg, Bremen, Brake, Nordenham und dem Jadebusen). Du kennst Rad- und Wanderwege (Weserradweg, Deichwege, Moorwege),
Ausflugsziele in der Wesermarsch, im Ammerland, an der Nordsee (Butjadingen, Dangast, Wilhelmshaven, Cuxhaven), in Bremen,
Oldenburg, Bremerhaven und weiter weg. Nutze die Websuche, um Öffnungszeiten, Preise und Saison zu prüfen (geschlossen im Winter?),
und um die offizielle Webseite jedes Ziels zu finden. Schlage nur Ziele vor, die zum Wetter, zur Jahreszeit, zur Zeit und zur
Entfernung passen; bei Regen auch Drinnen-Ziele. Mit Kind: kindgerecht. Ehrlich bleiben – nichts erfinden.
Antworte am Ende NUR mit JSON:
{"ideen": [{"name": "…", "kategorie": "Natur|Tiere|Spielplatz|Wellness|Baden|Museum|Stadt|Essen|Abenteuer|Strand|Drinnen",
  "kurz": "1 Satz", "beschreibung": "2–3 Sätze, was euch erwartet", "warum": "warum es heute passt",
  "adresse": "…", "lat": 53.3, "lon": 8.4, "entfernung_km": 18, "fahrzeit_min": 25, "drinnen": false,
  "oeffnung": "heute geöffnet …", "preis": "Erwachsene … / Kinder …", "webseite": "https://…",
  "zwischenstopps": [{"name": "…", "lat": 53.3, "lon": 8.4}],
  "ablauf": [{"zeit": "10:00", "was": "Abfahrt zu Hause"}], "tipps": ["…"], "mitnehmen": ["…"],
  "einkehr": "Café/Restaurant mit Name"}],
 "hinweis": "1 Satz zum Wetter/Tag"}
5 bis 6 Ideen, verschieden (nicht alles dieselbe Art). Bei Fahrrad: Rundtour, Entfernung = Tour gesamt in km; zwischenstopps =
2–3 schöne Punkte auf dem Weg (für die Route), die WIRKLICH zwischen Ovelgönne und dem Ziel liegen (kein Umweg).
Adresse immer vollständig mit Straße, PLZ und Ort (Google Maps findet das Ziel darüber). Koordinaten mit 4 Nachkommastellen
und nur, wenn du sie aus einer Quelle kennst – sonst lat/lon weglassen statt schätzen."""


def json_laden(pfad, leer):
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, type(leer)) else leer
    except (OSError, ValueError):
        return leer


def json_schreiben(pfad, d):
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, pfad)


def status(laeuft, text="", fehler=""):
    json_schreiben(STATUS, {"laeuft": laeuft, "text": text, "fehler": fehler, "zeit": datetime.now().isoformat(timespec="seconds")})


def zahl(v, standard=None):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return standard


def idee_sauber(x):
    t = lambda k, n=200: str(x.get(k) or "")[:n]   # noqa: E731
    return {"name": t("name", 80), "kategorie": t("kategorie", 20), "kurz": t("kurz"), "beschreibung": t("beschreibung", 500),
            "warum": t("warum", 240), "adresse": t("adresse", 160), "lat": zahl(x.get("lat")), "lon": zahl(x.get("lon")),
            "entfernung_km": zahl(x.get("entfernung_km")), "fahrzeit_min": zahl(x.get("fahrzeit_min")), "drinnen": bool(x.get("drinnen")),
            "oeffnung": t("oeffnung", 160), "preis": t("preis", 160),
            "webseite": t("webseite", 300) if str(x.get("webseite") or "").startswith("http") else "",
            "zwischenstopps": [{"name": str(z.get("name") or "")[:60], "lat": zahl(z.get("lat")), "lon": zahl(z.get("lon"))}
                               for z in x.get("zwischenstopps") or [] if isinstance(z, dict) and zahl(z.get("lat")) and zahl(z.get("lon"))][:4],
            "ablauf": [{"zeit": str(a.get("zeit") or "")[:10], "was": str(a.get("was") or "")[:140]}
                       for a in x.get("ablauf") or [] if isinstance(a, dict)][:8],
            "tipps": [str(a)[:140] for a in x.get("tipps") or []][:5], "mitnehmen": [str(a)[:60] for a in x.get("mitnehmen") or []][:8],
            "einkehr": t("einkehr", 140), "bild": ""}


def ideen_machen(auftrag):
    import kueche
    wie = auftrag.get("wie") or "Auto"
    wochentag = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][date.today().weekday()]
    frage = (f"Heute ist {wochentag}, {date.today().strftime('%d.%m.%Y')}.\n"
             f"Ausflug am: {auftrag.get('wann') or 'heute'} · Dauer: {auftrag.get('dauer') or 'halber Tag'}\n"
             f"Unterwegs mit: {wie} · Wie weit höchstens: {auftrag.get('weite') or 'egal'}\n"
             f"Wer kommt mit: {auftrag.get('wer') or 'Familie (2 Erwachsene, Tochter 8 Jahre)'}\n"
             f"Was wir mögen: {', '.join(auftrag.get('interessen') or []) or 'offen für alles'}\n"
             f"Wetter: {auftrag.get('wetter') or 'unbekannt'}\n"
             + (f"Besonderer Wunsch: {auftrag['wunsch']}\n" if auftrag.get("wunsch") else "")
             + (f"Waren schon da (nicht wieder vorschlagen): {', '.join(auftrag['erlebt'])}\n" if auftrag.get("erlebt") else ""))
    status(True, "Claude sucht Ausflugsziele und prüft Öffnungszeiten …")
    a = kueche.claude(SYSTEM, frage, max_tokens=12000, effort="medium", timeout=300,
                      werkzeuge=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 10,
                                  "user_location": {"type": "approximate", "city": "Ovelgönne", "region": "Niedersachsen",
                                                    "country": "DE", "timezone": "Europe/Berlin"}}])
    ideen = [idee_sauber(x) for x in a.get("ideen") or [] if isinstance(x, dict) and x.get("name")][:6]
    if not ideen:
        raise RuntimeError("Claude hat keine passenden Ziele gefunden – bitte Wünsche etwas weiter fassen")
    status(True, "Bilder werden geholt …")
    from concurrent.futures import ThreadPoolExecutor

    def bild(i):
        try:
            return kueche.og_bild(i["webseite"]) if i["webseite"] else ""
        except Exception:  # noqa: BLE001
            return ""
    with ThreadPoolExecutor(max_workers=6) as pool:
        for i, b in zip(ideen, pool.map(bild, ideen)):
            i["bild"] = b
    d = json_laden(DATEN, {})
    d["ideen"] = ideen
    d["anfrage"] = {k: auftrag.get(k) for k in ("wie", "wann", "dauer", "wer", "interessen", "weite", "wunsch")}
    d["hinweis"] = str(a.get("hinweis") or "")[:240]
    d["stand"] = datetime.now().isoformat(timespec="minutes")
    json_schreiben(DATEN, d)
    return f"{len(ideen)} Ausflugsideen: " + ", ".join(i["name"] for i in ideen)


def im_hintergrund(auftrag):
    if os.fork() > 0:
        return
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    fd = os.open(os.devnull, os.O_RDWR)
    for s in (0, 1, 2):
        os.dup2(fd, s)
    try:
        text = ideen_machen(auftrag)
        status(False, text)
        if auftrag.get("chat"):
            import kueche
            d = json_laden(DATEN, {})
            zeilen = []
            for i in d.get("ideen") or []:
                ort = f"{i['lat']},{i['lon']}" if i.get("lat") and i.get("lon") else (i.get("adresse") or i["name"]).replace(" ", "+")
                mehr = " · ".join(x for x in (f"{round(i['entfernung_km'])} km" if i.get("entfernung_km") else "",
                                              "drinnen" if i.get("drinnen") else "", i.get("preis", "")[:40]) if x)
                zeilen.append(f"• {i['name']} – {i['kurz']}" + (f" ({mehr})" if mehr else "")
                              + f"\n  Karte: https://www.google.com/maps/search/?api=1&query={ort}")
            kueche.senden(auftrag["chat"], "🚲 Ausflugsideen:\n" + "\n".join(zeilen)
                          + "\n\nAblauf, Bilder und Route ab Haustür am Monitor unter „Ausflug“.")
    except Exception as fehler:  # noqa: BLE001
        status(False, "", fehler=str(fehler)[:250] if isinstance(fehler, (RuntimeError, ValueError)) else f"{type(fehler).__name__}: {str(fehler)[:200]}")
    os._exit(0)


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else ""
    if aktion == "speichern":
        neu = json.loads(base64.b64decode("".join(sys.argv[2:])).decode("utf-8"))
        if not isinstance(neu, dict):
            raise ValueError("unerwartetes Format")
        json_schreiben(DATEN, neu)
        print(json.dumps({"ok": True}))
        return
    if aktion == "ki":
        auftrag = json.loads(base64.b64decode("".join(sys.argv[2:])).decode("utf-8"))
        alt = json_laden(STATUS, {})
        if alt.get("laeuft") and time.time() - os.path.getmtime(STATUS) < 500:
            raise RuntimeError("Claude sucht schon – bitte kurz warten")
        status(True, "Claude legt los …")
        im_hintergrund(auftrag)
        print(json.dumps({"ok": True}))
        return
    raise ValueError("unbekannte Aktion")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": str(fehler)[:250]}, ensure_ascii=False))
