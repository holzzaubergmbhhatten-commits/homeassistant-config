#!/usr/bin/env python3
"""Grundriss-Anordnung speichern (Aufruf aus script.grundriss_speichern).

Argument: Base64 des JSON {raeume:[...], lampen:[...], foto?:{...}}.
Schreibt /config/www/grundriss_daten.json (lokal, nicht im Repository); die vorherige
Fassung bleibt als grundriss_daten.vorher.json erhalten.
"""
import base64
import json
import os
import shutil
import sys

ZIEL = "/config/www/grundriss_daten.json"


def main():
    daten = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
    if not (isinstance(daten, dict) and isinstance(daten.get("raeume"), list) and isinstance(daten.get("lampen"), list)):
        raise ValueError("unerwartetes Format")
    if os.path.exists(ZIEL):
        shutil.copy2(ZIEL, ZIEL.replace(".json", ".vorher.json"))
    tmp = ZIEL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ZIEL)
    print(f"ok · {len(daten['raeume'])} Räume, {len(daten['lampen'])} Lampen")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(f"Fehler: {fehler}")
