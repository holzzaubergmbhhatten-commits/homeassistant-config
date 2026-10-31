#!/usr/bin/env python3
"""Alltagshelfer für packages/alltag.yaml – alles lokal, ohne Schlüssel:

  alltag.py schule                 Was Mathilda morgen braucht (aus dem Stundenplan auf Muckis Seite) + ob morgen Ferien sind
  alltag.py ferien                 Schulferien Niedersachsen (ferien-api.de, einmal am Tag zwischengespeichert)
  alltag.py ferien_neu             Ferien, die noch nicht im Familienkalender stehen (werden als eingetragen gemerkt)
  alltag.py dwd                    Unwetterwarnungen des Deutschen Wetterdienstes für die Wesermarsch
  alltag.py dokument <base64-JSON {text, von}>   „Reisepass Mathilda läuft am 12.05.2027 ab“ merken
  alltag.py dokumente              Liste der Ausweise/Pässe mit Ablaufdatum (für Erinnerungen)
  alltag.py hausarbeit             Aufgaben der Woche (feste Liste, wechselnd verteilt) – Datei /config/hausarbeit.json

Ausgabe immer JSON. Daten nur lokal in /config (nicht im Repository).
"""
import base64
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta

MUCKI = "/config/www/mucki_daten.json"
FERIEN = "/config/schulferien.json"
FERIEN_EINGETRAGEN = "/config/schulferien_eingetragen.json"
DOKUMENTE = "/config/dokumente.json"
HAUSARBEIT = "/config/hausarbeit.json"
TAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Was zu welchem Fach in die Tasche gehört (Rest: nur das Fach nennen)
EINPACKEN = [
    (r"schwimm", "Badesachen, Handtuch, Duschgel, Haargummi"),
    (r"\bsport|turnen", "Sportzeug und Hallenschuhe"),
    (r"kunst|werken|textil", "Malkittel und Farbkasten"),
    (r"musik", "Musikheft"),
    (r"religion|\bwn\b|werte", "Religionsheft"),
]

# Standard-Hausarbeit (Datei /config/hausarbeit.json überschreibt): wer = Reihenfolge, die jede Woche weiterrückt
HAUSARBEIT_STANDARD = {
    "personen": ["Marco", "Mirka"],
    "kind": "Mathilda",
    "aufgaben": [
        {"titel": "Bad putzen", "alle_wochen": 1},
        {"titel": "Staubsaugen und wischen", "alle_wochen": 1},
        {"titel": "Küche gründlich (Herd, Kühlschrank auswischen)", "alle_wochen": 2},
        {"titel": "Bettwäsche wechseln", "alle_wochen": 2},
        {"titel": "Altglas und Pfand wegbringen", "alle_wochen": 2},
        {"titel": "Fenster putzen", "alle_wochen": 8},
    ],
    "kinder_aufgaben": [
        {"titel": "Zimmer aufräumen", "alle_wochen": 1},
        {"titel": "Tisch decken helfen", "alle_wochen": 1},
        {"titel": "Blumen gießen", "alle_wochen": 1},
    ],
}


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


def holen(url):
    req = urllib.request.Request(url, headers={"User-Agent": "HomeAssistant-Familie"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


# ---------- Schulferien ----------

def ferien_liste():
    """Schulferien Niedersachsen (dieses und nächstes Jahr), einmal am Tag neu geholt."""
    d = json_laden(FERIEN, {})
    if d.get("stand") != date.today().isoformat():
        try:
            neu = json.loads(holen("https://ferien-api.de/api/v1/holidays/NI"))
            liste = [{"name": re.sub(r"(?i)\s*niedersachsen.*$", "", str(f.get("name", "Ferien"))).strip().title() or "Ferien",
                      "start": str(f.get("start", ""))[:10], "ende": str(f.get("end", ""))[:10]}
                     for f in neu if isinstance(f, dict) and f.get("start")]
            if liste:
                d = {"stand": date.today().isoformat(), "liste": liste}
                json_schreiben(FERIEN, d)
        except Exception:  # noqa: BLE001 – dann gilt der letzte Stand
            pass
    return d.get("liste") or []


def in_ferien(tag, liste):
    return next((f for f in liste if f["start"] <= tag.isoformat() <= f["ende"]), None)


# ---------- Schule ----------

def schule():
    morgen = date.today() + timedelta(days=1)
    ferien = ferien_liste()
    f = in_ferien(morgen, ferien)
    aus = {"tag": TAGE[morgen.weekday()], "schule": False, "faecher": [], "einpacken": [], "ferien": f["name"] if f else ""}
    if morgen.weekday() > 4 or f:
        return aus
    d = json_laden(MUCKI, {})
    faecher = []
    for z in d.get("zeilen") or []:
        liste = z.get("faecher") or []
        if not z.get("info") and morgen.weekday() < len(liste):
            fach = str((liste[morgen.weekday()] or {}).get("fach", "")).strip()
            if fach and fach.lower() not in ("betreuung", "-", "") and fach not in faecher:
                faecher.append(fach)
    einpacken = []
    for fach in faecher:
        for muster, sachen in EINPACKEN:
            if re.search(muster, fach, re.I) and sachen not in einpacken:
                einpacken.append(sachen)
    aus.update(schule=bool(faecher), faecher=faecher, einpacken=einpacken)
    return aus


# ---------- Unwetter (DWD) ----------

TIPPS = [
    (r"sturm|orkan|wind", "Gartenmöbel, Trampolin und Mülltonnen sichern, Wohnwagen-Markise einfahren, Fenster zu"),
    (r"frost", "Empfindliche Pflanzen reinholen oder abdecken, Gartenschlauch und Außenhahn leeren"),
    (r"glätte|glatteis|schnee", "Wege streuen, mehr Zeit für den Weg einplanen"),
    (r"gewitter|starkregen|dauerregen|hagel", "Dachrinnen und Abläufe frei? Kellerfenster zu, Auto nicht unter Bäume stellen"),
    (r"hitze", "Viel trinken, tagsüber Fenster zu und Rollos runter, morgens lüften"),
    (r"nebel", "Langsam fahren"),
]


def dwd():
    """Aktuelle Warnungen für den Landkreis Wesermarsch (Warn-App-Daten des DWD)."""
    roh = holen("https://www.dwd.de/DWD/warnungen/warnapp/json/warnings.json")
    m = re.search(r"\((\{.*\})\)", roh, re.S)
    daten = json.loads(m.group(1) if m else roh)
    aus = []
    for bereich in ("warnings", "vorabInformation"):
        for zelle, warnungen in (daten.get(bereich) or {}).items():
            for w in warnungen or []:
                if "wesermarsch" not in str(w.get("regionName", "")).lower():
                    continue
                ereignis = str(w.get("event", "")).strip()
                tipp = next((t for muster, t in TIPPS if re.search(muster, ereignis, re.I)), "")
                start = datetime.fromtimestamp(int(w.get("start") or 0) / 1000) if w.get("start") else None
                ende = datetime.fromtimestamp(int(w.get("end") or 0) / 1000) if w.get("end") else None
                aus.append({"id": f"{ereignis}-{w.get('start')}", "ereignis": ereignis.title(), "stufe": int(w.get("level") or 0),
                            "titel": str(w.get("headline", ""))[:120], "text": str(w.get("description", ""))[:400],
                            "von": start.strftime("%a %d.%m. %H:%M") if start else "", "bis": ende.strftime("%a %d.%m. %H:%M") if ende else "",
                            "tipp": tipp, "vorab": bereich == "vorabInformation"})
    uebersetzen = {"Mon": "Mo", "Tue": "Di", "Wed": "Mi", "Thu": "Do", "Fri": "Fr", "Sat": "Sa", "Sun": "So"}
    for w in aus:
        for en, de in uebersetzen.items():
            w["von"], w["bis"] = w["von"].replace(en, de), w["bis"].replace(en, de)
    eindeutig = {w["id"]: w for w in aus}
    return {"warnungen": sorted(eindeutig.values(), key=lambda w: -w["stufe"])}


# ---------- Ausweise & Pässe ----------

DATUM = r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})|(\d{1,2})[./](\d{4})"


def dokument_merken(auftrag):
    text = str(auftrag.get("text") or "")
    m = re.search(DATUM, text)
    if not m:
        return {"ok": False, "fehler": "Kein Datum gefunden – bitte so schicken: „Reisepass Mathilda läuft am 12.05.2027 ab“"}
    if m.group(1):
        j = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
        ablauf = date(j, int(m.group(2)), int(m.group(1)))
    else:
        monat, jahr = int(m.group(4)), int(m.group(5))
        ablauf = (date(jahr + (monat == 12), monat % 12 + 1, 1) - timedelta(days=1))
    art = next((a for a in ("Kinderreisepass", "Reisepass", "Personalausweis", "Führerschein", "Ausweis", "Krankenkassenkarte", "EC-Karte",
                            "Kreditkarte", "Pass") if a.lower() in text.lower()), "Dokument")
    person = next((p for p in ("Mathilda", "Mirka", "Marco") if p.lower() in text.lower()), auftrag.get("von") or "")
    liste = [x for x in json_laden(DOKUMENTE, []) if not (x.get("art") == art and x.get("person") == person)]
    liste.append({"art": art, "person": person, "ablauf": ablauf.isoformat(), "erinnert": []})
    json_schreiben(DOKUMENTE, sorted(liste, key=lambda x: x["ablauf"]))
    return {"ok": True, "text": f"{art} {person}: läuft am {ablauf.strftime('%d.%m.%Y')} ab – ich erinnere 3 Monate und 1 Monat vorher."}


def dokumente():
    """Liste + was heute zu erinnern ist (90 und 30 Tage vorher, je einmal)."""
    liste = json_laden(DOKUMENTE, [])
    heute = date.today()
    faellig = []
    for x in liste:
        tage = (date.fromisoformat(x["ablauf"]) - heute).days
        for stufe in (90, 30, 0):
            if tage <= stufe and stufe not in (x.get("erinnert") or []):
                x.setdefault("erinnert", []).append(stufe)
                faellig.append(dict(x, tage=tage))
                break
    if faellig:
        json_schreiben(DOKUMENTE, liste)
    return {"liste": [dict(x, tage=(date.fromisoformat(x["ablauf"]) - heute).days) for x in liste], "faellig": faellig}


# ---------- Hausarbeit ----------

def hausarbeit():
    plan = json_laden(HAUSARBEIT, {}) or HAUSARBEIT_STANDARD
    if not os.path.exists(HAUSARBEIT):
        json_schreiben(HAUSARBEIT, HAUSARBEIT_STANDARD)
    woche = date.today().isocalendar()[1]
    personen = plan.get("personen") or ["Marco", "Mirka"]
    aus = []
    for i, a in enumerate(plan.get("aufgaben") or []):
        n = int(a.get("alle_wochen") or 1)
        if woche % n == 0 or n == 1:
            wer = personen[(woche // n + i) % len(personen)]
            aus.append(f"{a['titel']} ({wer})")
    for a in plan.get("kinder_aufgaben") or []:
        n = int(a.get("alle_wochen") or 1)
        if woche % n == 0 or n == 1:
            aus.append(f"{a['titel']} ({plan.get('kind') or 'Mathilda'})")
    return {"woche": woche, "aufgaben": aus}


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else ""
    auftrag = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8")) if len(sys.argv) > 2 and sys.argv[2] else {}
    if aktion == "schule":
        aus = schule()
    elif aktion == "ferien":
        liste = ferien_liste()
        heute = date.today().isoformat()
        aus = {"liste": liste, "jetzt": (in_ferien(date.today(), liste) or {}).get("name", ""),
               "naechste": next((f for f in liste if f["start"] > heute), {})}
    elif aktion == "ferien_neu":
        eingetragen = json_laden(FERIEN_EINGETRAGEN, [])
        neu = [f for f in ferien_liste() if f["ende"] >= date.today().isoformat() and f"{f['name']}|{f['start']}" not in eingetragen]
        json_schreiben(FERIEN_EINGETRAGEN, eingetragen + [f"{f['name']}|{f['start']}" for f in neu])
        aus = {"neu": [dict(f, ende_plus=(date.fromisoformat(f["ende"]) + timedelta(days=1)).isoformat()) for f in neu]}
    elif aktion == "dwd":
        aus = dwd()
    elif aktion == "dokument":
        aus = dokument_merken(auftrag)
    elif aktion == "dokumente":
        aus = dokumente()
    elif aktion == "hausarbeit":
        aus = hausarbeit()
    else:
        raise ValueError("unbekannte Aktion")
    print(json.dumps(aus, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": f"{type(fehler).__name__}: {fehler}"[:200], "warnungen": [], "liste": [],
                          "faellig": [], "neu": [], "aufgaben": [], "faecher": [], "einpacken": []}, ensure_ascii=False))
