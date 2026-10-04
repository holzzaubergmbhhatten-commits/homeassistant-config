#!/usr/bin/env python3
"""Muckis Seite speichern (Aufruf aus script.mucki_speichern).

Argument: Base64 des JSON {version, titel, klasse, zeilen:[...], aufgaben:[...], taschengeld:{...}}.
Schreibt /config/www/mucki_daten.json (bleibt lokal, nicht im öffentlichen Repository – dort
stehen z. B. Lehrernamen); die vorherige Fassung bleibt als mucki_daten.vorher.json erhalten.
"""
import base64
import json
import os
import shutil
import sys

ZIEL = "/config/www/mucki_daten.json"


def main():
    daten = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
    if not (isinstance(daten, dict) and isinstance(daten.get("zeilen"), list) and isinstance(daten.get("aufgaben"), list)):
        raise ValueError("unerwartetes Format")
    os.makedirs(os.path.dirname(ZIEL), exist_ok=True)
    if os.path.exists(ZIEL):
        shutil.copy2(ZIEL, ZIEL.replace(".json", ".vorher.json"))
    tmp = ZIEL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ZIEL)
    print(f"ok · {len(daten['zeilen'])} Zeilen, {len(daten['aufgaben'])} Aufgaben")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(f"Fehler: {fehler}")
