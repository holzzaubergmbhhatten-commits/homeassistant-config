#!/usr/bin/env python3
"""Muckis Taschengeld-Woche abschließen (Aufruf aus script.mucki_woche_abschliessen).

Argument: Base64 des JSON {"woche": "2026-W40", "aufgaben": ["Rasenmähen", ...], "lernen": 3}.
Hängt die Aufgaben an die Kalenderwoche in /config/www/mucki_verlauf.json an
(lokal, nicht im Repository). Wird dieselbe Woche zweimal abgeschlossen, werden die
Aufgaben zusammengeführt (höchstens 6 zählen).
"""
import base64
import json
import os
import re
import sys

ZIEL = "/config/www/mucki_verlauf.json"


def main():
    neu = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
    woche = str(neu.get("woche", ""))
    if not re.fullmatch(r"\d{4}-W\d{2}", woche):
        raise ValueError(f"unbekannte Woche {woche!r}")
    aufgaben = [str(a) for a in neu.get("aufgaben", []) if str(a).strip()]
    verlauf = {}
    if os.path.exists(ZIEL):
        with open(ZIEL, encoding="utf-8") as f:
            verlauf = json.load(f)
    wochen = verlauf.setdefault("wochen", {})
    wochen[woche] = (wochen.get(woche, []) + aufgaben)[:6]
    lernen = int(neu.get("lernen") or 0)
    if lernen:
        lern = verlauf.setdefault("lernen", {})
        lern[woche] = max(int(lern.get(woche, 0)), lernen)
    tmp = ZIEL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(verlauf, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ZIEL)
    print(f"ok · {woche}: {len(wochen[woche])} Aufgaben, {lernen} Lernaufgaben")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(f"Fehler: {fehler}")
