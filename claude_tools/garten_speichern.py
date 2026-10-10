#!/usr/bin/env python3
"""Gartenplan speichern (Aufruf aus script.garten_speichern).

Argumente: Base64 des JSON {version, karte, pflanzungen, wunsch, historie, fotos}, in
Stücke geteilt (lange Texte passen nicht in ein einzelnes Argument) – hier wieder zusammengesetzt.
Schreibt /config/www/garten_daten.json (bleibt lokal, nicht im öffentlichen Repository);
die vorherige Fassung bleibt als garten_daten.vorher.json erhalten.
"""
import base64
import json
import os
import shutil
import sys

ZIEL = "/config/www/garten_daten.json"


def main():
    daten = json.loads(base64.b64decode("".join(sys.argv[1:])).decode("utf-8"))
    if not (isinstance(daten, dict) and isinstance(daten.get("karte"), dict) and isinstance(daten["karte"].get("beete"), list)):
        raise ValueError("unerwartetes Format")
    os.makedirs(os.path.dirname(ZIEL), exist_ok=True)
    if os.path.exists(ZIEL):
        shutil.copy2(ZIEL, ZIEL.replace(".json", ".vorher.json"))
    tmp = ZIEL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False)
    os.replace(tmp, ZIEL)
    print(f"ok · {len(daten['karte']['beete'])} Beete, {len(daten.get('pflanzungen', []))} Pflanzungen")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(f"Fehler: {fehler}")
