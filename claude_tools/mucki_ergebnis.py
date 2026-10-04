#!/usr/bin/env python3
"""Muckis Taschengeld dieser Woche ausrechnen (für die Sonntags-Erinnerung).

Argument: Base64 des JSON {"woche": "2026-W41", "felder": [...], "lernen": 3}.
Liest Einstellungen aus /config/www/mucki_daten.json und den Verlauf aus
/config/www/mucki_verlauf.json (beide lokal) und gibt JSON aus:
{"felder": 6, "lernen": 3, "grund": 2.0, "verdient": 3.0, "lernbonus": 1.0, "bonus": 1.0, "gesamt": 7.0, "alles": true}
"""
import base64
import datetime
import json
import os
import re
import sys

DATEN = "/config/www/mucki_daten.json"
VERLAUF = "/config/www/mucki_verlauf.json"


def zahl(text):
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(text or ""))
    return float(m.group(1).replace(",", ".")) if m else 0.0


def lesen(pfad):
    if os.path.exists(pfad):
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    return {}


def vorwoche(woche):
    jahr, kw = woche.split("-W")
    montag = datetime.date.fromisocalendar(int(jahr), int(kw), 1) - datetime.timedelta(days=7)
    j, w, _ = montag.isocalendar()
    return f"{j}-W{w:02d}"


def main():
    neu = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
    tg = lesen(DATEN).get("taschengeld") or {}
    woche_text = tg.get("woche", "5 €")
    posten = tg.get("posten") or [{"betrag": "2"}, {"betrag": "1"}]
    cent = tg.get("cent") or 50
    bonus_betrag = 1.0 if tg.get("bonus") is None else float(tg.get("bonus"))
    lern_betrag = 1.0 if tg.get("lernBonus") is None else float(tg.get("lernBonus"))
    felder = len([a for a in neu.get("felder", []) if str(a).strip()])
    lernen = int(neu.get("lernen") or 0)
    grund = zahl(woche_text) - sum(zahl(p.get("betrag")) for p in posten)
    verdient = felder * cent / 100
    lernbonus = lern_betrag if lernen >= 3 else 0.0
    wochen = (lesen(VERLAUF).get("wochen") or {})
    bonus = bonus_betrag if felder >= 6 and len(wochen.get(vorwoche(neu["woche"]), [])) >= 6 else 0.0
    gesamt = grund + verdient + lernbonus + bonus
    print(json.dumps({"felder": felder, "lernen": lernen, "grund": grund, "verdient": verdient,
                      "lernbonus": lernbonus, "bonus": bonus, "gesamt": gesamt,
                      "alles": felder >= 6 and lernen >= 3}))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"fehler": str(fehler)}))
