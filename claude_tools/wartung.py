#!/usr/bin/env python3
"""Wartungskalender für Home Assistant (Aufruf aus packages/wartung.yaml).

Die Aufgaben (was, wie oft, Hinweis) kommen von der Wartungsseite des Haus-Handbuchs (wartung.html,
Liste "const T=[...]"). Die Adresse steht nur in Home Assistant (input_text.zuhause_seite_link), nicht im
Repository. Wann etwas zuletzt erledigt wurde, merkt sich Home Assistant in /config/wartung_daten.json
(lokal, nicht öffentlich).

Aufrufe:
  wartung.py laden <link> [neu]       Liste von der Seite holen (höchstens alle 6 Stunden, "neu" = sofort)
  wartung.py erledigt <key> <datum>   als erledigt merken (datum JJJJ-MM-TT oder "heute")
  wartung.py offen <key> -            "erledigt" zurücknehmen
Ausgabe immer JSON: {"alle": [...], "anstehend": [...], "ohne_datum": n, "stand": "...", "fehler": "..."}
"""
import calendar
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

DATEN = "/config/wartung_daten.json"
BALD_TAGE = 21

# Jahreszeit aus dem Hinweis: Aufgaben ohne Datum stehen dann zur passenden Zeit an
JAHRESZEIT = [
    (r"oktober|november|vor (dem )?frost|winterfest|vor dem winter|saisonende", [10, 11]),
    (r"vor der heizsaison", [9, 10]),
    (r"herbst", [9, 10, 11]),
    (r"frühjahr|fruehjahr", [3, 4, 5]),
    (r"winterlager", [11, 12, 1, 2, 3]),
    (r"in der heizsaison", [10, 11, 12, 1, 2, 3]),
]


def schluessel(text):
    t = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60]


def laden_datei():
    try:
        with open(DATEN, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def speichern(d):
    tmp = DATEN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATEN)


def seite_holen(link):
    """wartung.html neben der Startseite des Handbuchs laden und die Liste T auslesen."""
    basis = link.strip()
    if not re.match(r"^https?://", basis):
        raise ValueError("Kein Link zur Infos-Seite eingetragen")
    if not basis.endswith("/") and not basis.rsplit("/", 1)[-1].count("."):
        basis += "/"
    url = urllib.parse.urljoin(basis, "wartung.html")
    req = urllib.request.Request(url, headers={"User-Agent": "HomeAssistant-Wartung", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode("utf-8", "replace")
    m = re.search(r"const\s+T\s*=\s*\[(.*?)\n\s*\];", text, re.S)
    if not m:
        raise ValueError("Wartungsliste auf der Seite nicht gefunden")
    zeilen = re.findall(r'\[\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*,\s*(\d+)\s*,\s*"((?:[^"\\]|\\.)*)"\s*\]', m.group(1))
    aufgaben, gesehen = [], set()
    for bereich, titel, monate, hinweis in zeilen:
        bereich, titel, hinweis = (html.unescape(x).strip() for x in (bereich, titel, hinweis))
        # doppelte Einträge (z. B. FI-Test zweimal) nur einmal: gleicher Anfang = gleiche Aufgabe
        kurz = re.sub(r"[^a-z]", "", titel.lower())[:22]
        if kurz in gesehen:
            alt = next(a for a in aufgaben if re.sub(r"[^a-z]", "", a["titel"].lower())[:22] == kurz)
            if len(hinweis) > len(alt["hinweis"]):
                alt.update(titel=titel, hinweis=hinweis)
            continue
        gesehen.add(kurz)
        aufgaben.append({"key": schluessel(titel), "bereich": bereich, "titel": titel, "intervall": int(monate), "hinweis": hinweis})
    if not aufgaben:
        raise ValueError("Wartungsliste ist leer")
    return aufgaben


def plus_monate(d, n):
    m = d.month - 1 + n
    j, m = d.year + m // 12, m % 12 + 1
    return date(j, m, min(d.day, calendar.monthrange(j, m)[1]))


def auswerten(d):
    heute = date.today()
    erledigt = d.get("erledigt") or {}
    alle, anstehend, ohne = [], [], 0
    for a in d.get("aufgaben") or []:
        e = dict(a)
        zuletzt = erledigt.get(a["key"])
        monate = (d.get("intervall") or {}).get(a["key"], a["intervall"])
        e["intervall"] = monate
        if zuletzt:
            faellig = plus_monate(date.fromisoformat(zuletzt), monate)
            tage = (faellig - heute).days
            e.update(zuletzt=zuletzt, faellig_am=faellig.isoformat(), tage=tage,
                     status="ueberfaellig" if tage < 0 else "bald" if tage <= BALD_TAGE else "ok")
        else:
            text = (a["titel"] + " " + a["hinweis"]).lower()
            monate_saison = next((ms for muster, ms in JAHRESZEIT if re.search(muster, text)), None)
            e["status"] = "jetzt" if monate_saison and heute.month in monate_saison else "ohne"
            if e["status"] == "ohne":
                ohne += 1
        alle.append(e)
        if e["status"] in ("ueberfaellig", "jetzt", "bald"):
            anstehend.append({k: e[k] for k in ("key", "bereich", "titel", "status") if k in e} | ({"tage": e["tage"]} if "tage" in e else {}))
    rang = {"ueberfaellig": 0, "jetzt": 1, "bald": 2}
    anstehend.sort(key=lambda x: (rang[x["status"]], x.get("tage", 0)))
    return {"alle": alle, "anstehend": anstehend, "ohne_datum": ohne, "stand": d.get("stand", ""), "fehler": d.get("fehler", "")}


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else "laden"
    wert = sys.argv[2] if len(sys.argv) > 2 else ""
    extra = sys.argv[3] if len(sys.argv) > 3 else ""
    d = laden_datei()
    if aktion == "laden":
        alt = d.get("geholt", "")
        zu_alt = not alt or datetime.now() - datetime.fromisoformat(alt) > timedelta(hours=6)
        if extra == "neu" or zu_alt or not d.get("aufgaben"):
            try:
                d["aufgaben"] = seite_holen(wert)
                d["stand"] = datetime.now().strftime("%d.%m.%Y %H:%M")
                d["fehler"] = ""
            except Exception as fehler:  # noqa: BLE001 – dann bleibt die letzte Liste
                d["fehler"] = f"Seite nicht erreichbar: {fehler}"[:200]
            d["geholt"] = datetime.now().isoformat(timespec="seconds")
            speichern(d)
    elif aktion in ("erledigt", "offen"):
        keys = {a["key"] for a in d.get("aufgaben") or []}
        if wert not in keys:
            raise ValueError("Unbekannte Aufgabe")
        d.setdefault("erledigt", {})
        if aktion == "offen":
            d["erledigt"].pop(wert, None)
        else:
            tag = date.today() if extra in ("", "heute") else date.fromisoformat(extra)
            d["erledigt"][wert] = min(tag, date.today()).isoformat()
        speichern(d)
    print(json.dumps(auswerten(d), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"alle": [], "anstehend": [], "ohne_datum": 0, "fehler": f"{type(fehler).__name__}: {fehler}"[:200]}, ensure_ascii=False))
