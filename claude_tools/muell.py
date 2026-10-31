#!/usr/bin/env python3
"""Müllabfuhr (GIB Wesermarsch) für Monitor, Morgen-Nachricht und Telegram (packages/muell.yaml).

Die Termine kommen als Kalender (iCal/ICS) aus der GIB-Abfall-App oder von gib-entsorgung.de:
  muell.py link <base64-Text>    Link aus der Nachricht "Müll-Link: https://…" merken (webcal:// geht auch) und gleich holen
  muell.py datei <base64-JSON {datei}>   ICS-Datei (per Telegram geschickt) übernehmen
  muell.py foto <base64-JSON {datei}>    Screenshot der Terminliste aus der GIB-App (per Telegram mit Text „Müll“) –
                                 Claude liest die Termine ab, sie werden zu den vorhandenen dazugelegt
  muell.py holen                 Termine neu laden (einmal am Tag) und den Stand ausgeben
  muell.py stand                 nur den Stand ausgeben (für sensor.muell)
Link und Termine bleiben lokal (/config/muell_link.txt, /config/muell.json) – die Adresse steht nicht im Repository.
Ausgabe immer JSON: {"naechste": [{"datum", "art", "icon"}], "heute": [...], "morgen": [...], "hinweis": [...], "text"}.
"""
import base64
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

LINK = "/config/muell_link.txt"
DATEN = "/config/muell.json"
TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def art_icon(art):
    a = art.lower()
    if re.search(r"gelb|wertstoff|verpackung|lvp", a):
        return "mdi:recycle"
    if re.search(r"papier|pappe|blau", a):
        return "mdi:newspaper-variant-outline"
    if re.search(r"bio|grün|gruen|garten|laub|baum", a):
        return "mdi:leaf"
    if re.search(r"sperr|schadstoff|elektro", a):
        return "mdi:sofa-outline"
    return "mdi:trash-can-outline"


def ics_lesen(text):
    """Termine (Datum, Art) aus einem iCal-Text – nur einzelne Termine, keine Serienregeln (so liefern Abfallkalender)."""
    text = re.sub(r"\r?\n[ \t]", "", text)    # umgebrochene Zeilen zusammenfügen
    termine = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        start = re.search(r"^DTSTART[^:\n]*:(\d{8})", block, re.M)
        titel = re.search(r"^SUMMARY[^:\n]*:(.*)$", block, re.M)
        if not start or not titel:
            continue
        art = titel.group(1).strip().replace("\\,", ",").replace("\\n", " ").replace("\\", "")
        art = re.sub(r"(?i)^(abfuhr|leerung|abholung)\s*[:\-–]?\s*", "", art).strip() or "Müll"
        d = datetime.strptime(start.group(1), "%Y%m%d").date().isoformat()
        termine.append({"datum": d, "art": art[:60]})
    return sorted({(t["datum"], t["art"]): t for t in termine}.values(), key=lambda t: (t["datum"], t["art"]))


def speichern(termine, quelle, dazu=False):
    if not termine:
        raise ValueError("Im Kalender stehen keine Abfuhrtermine")
    alt = json_laden()
    if dazu:
        # Screenshots: zu den vorhandenen Terminen dazulegen (jedes Bild zeigt nur einen Ausschnitt)
        alle = {(t["datum"], t["art"]): t for t in alt.get("termine", []) + termine}
        termine, behalten = sorted(alle.values(), key=lambda t: (t["datum"], t["art"])), []
    else:
        # ältere Termine behalten, neue Daten ersetzen den Zeitraum der Datei
        von = termine[0]["datum"]
        behalten = [t for t in alt.get("termine", []) if t["datum"] < von]
    d = {"termine": behalten + termine, "stand": datetime.now().isoformat(timespec="minutes"), "quelle": quelle}
    tmp = DATEN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, DATEN)


def foto_lesen(pfad):
    """Abfuhrtermine von einem Screenshot ablesen (Claude, Schlüssel aus der Anthropic-Integration)."""
    if not os.path.realpath(pfad).startswith("/media/eingang/"):
        raise ValueError("Pfad nicht erlaubt")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import kueche
    with open(pfad, "rb") as f:
        bild = base64.b64encode(f.read()).decode("ascii")
    a = kueche.claude("Du liest Abfuhrtermine aus Screenshots einer Müll-App ab. Antworte nur mit JSON.", [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": bild}},
        {"type": "text", "text": f"Heute ist {date.today().isoformat()}. Lies ALLE sichtbaren Abfuhrtermine ab (nur vollständig sichtbare "
                                 "Einträge mit Datum darüber). Antworte nur mit JSON: {\"termine\": [{\"datum\": \"JJJJ-MM-TT\", "
                                 "\"art\": \"Biotonne\"}]} – art genau wie angezeigt, z. B. \"Restmülltonne (verlegt)\"."}],
        max_tokens=3000, effort="low", timeout=50)
    termine = [{"datum": t["datum"], "art": str(t.get("art", "Müll")).strip()[:60]} for t in a.get("termine") or []
               if isinstance(t, dict) and re.match(r"^\d{4}-\d\d-\d\d$", str(t.get("datum", "")))]
    return termine


def json_laden():
    try:
        with open(DATEN, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def holen(erzwingen=False):
    try:
        with open(LINK, encoding="utf-8") as f:
            link = f.read().strip()
    except OSError:
        return "kein Link"
    stand = json_laden().get("stand", "")
    if not erzwingen and stand[:10] == date.today().isoformat():
        return "aktuell"
    import urllib.request
    req = urllib.request.Request(link, headers={"User-Agent": "HomeAssistant-Muell"})
    with urllib.request.urlopen(req, timeout=25) as r:
        text = r.read().decode("utf-8", "replace")
    speichern(ics_lesen(text), "link")
    return "geladen"


def stand():
    heute = date.today()
    jetzt = datetime.now()
    termine = [t for t in json_laden().get("termine", []) if t["datum"] >= heute.isoformat()]
    for t in termine:
        t["icon"] = art_icon(t["art"])
        d = date.fromisoformat(t["datum"])
        t["tag"] = f"{TAGE[d.weekday()]} {d.strftime('%d.%m.')}"
    h = [t["art"] for t in termine if t["datum"] == heute.isoformat()]
    m = [t["art"] for t in termine if t["datum"] == (heute + timedelta(days=1)).isoformat()]
    hinweis = []
    if h and jetzt.hour < 10:
        hinweis.append("Heute wird abgeholt: " + ", ".join(h))
    if m and jetzt.hour >= 12:
        hinweis.append("Morgen wird abgeholt: " + ", ".join(m) + " – heute Abend rausstellen")
    if not json_laden().get("termine"):
        text = "Noch kein Müll-Kalender – Link aus der GIB-Abfall-App an den Bot schicken („Müll-Link: …“)"
    elif termine:
        tage = {}
        for t in termine:
            tage.setdefault(t["tag"], []).append(t["art"])
        text = " · ".join(f"{tag}: {', '.join(arten)}" for tag, arten in list(tage.items())[:3])
    else:
        text = "Keine Termine mehr im Kalender – bitte den neuen Kalender schicken"
    return {"naechste": termine[:8], "heute": h, "morgen": m, "hinweis": hinweis, "text": text,
            "bis": termine[-1]["datum"] if termine else ""}


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else "stand"
    wert = base64.b64decode(sys.argv[2]).decode("utf-8") if len(sys.argv) > 2 and sys.argv[2] else ""
    meldung = ""
    if aktion == "link":
        m = re.search(r"(webcal|https?)://\S+", wert)
        if not m:
            raise ValueError("Kein Link gefunden – bitte so schicken: Müll-Link: https://…")
        link = re.sub(r"^webcal://", "https://", m.group(0).rstrip(").,>"))
        with open(LINK, "w", encoding="utf-8") as f:
            f.write(link)
        meldung = holen(erzwingen=True)
    elif aktion == "datei":
        pfad = json.loads(wert).get("datei", "")
        if not os.path.realpath(pfad).startswith("/media/"):
            raise ValueError("Pfad nicht erlaubt")
        with open(pfad, encoding="utf-8", errors="replace") as f:
            speichern(ics_lesen(f.read()), "datei")
        os.remove(pfad)
        meldung = "datei"
    elif aktion == "foto":
        pfad = json.loads(wert).get("datei", "")
        neu = foto_lesen(pfad)
        speichern(neu, "foto", dazu=True)
        os.remove(pfad)
        meldung = f"{len(neu)} Termine vom Bild übernommen"
    elif aktion == "holen":
        try:
            meldung = holen()
        except Exception as fehler:  # noqa: BLE001 – dann gilt der letzte Stand
            meldung = f"Fehler beim Laden: {type(fehler).__name__}"
    aus = stand()
    aus["meldung"] = meldung
    print(json.dumps(aus, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"fehler": f"{type(fehler).__name__}: {fehler}"[:200], "naechste": [], "heute": [], "morgen": [],
                          "hinweis": [], "text": ""}, ensure_ascii=False))
