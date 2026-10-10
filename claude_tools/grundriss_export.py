#!/usr/bin/env python3
"""Grundriss als Datei (Aufruf aus script.grundriss_datei_teil): ein Stück einer Datei schreiben.

Argumente: Dateiname (nur grundriss_*.svg/.png), "neu" oder "dazu", Base64-Stück (Länge durch 4 teilbar).
Die Seite schickt große Dateien in mehreren Stücken (eine Vorlage in Home Assistant darf nicht beliebig lang
werden). Ziel: /media/grundriss_export/ (dort darf der Telegram-Bot Dateien verschicken; nicht öffentlich).
"""
import base64
import os
import re
import sys

ZIEL = "/media/grundriss_export"


def main():
    name, modus, teil = sys.argv[1], sys.argv[2], "".join(sys.argv[3:])
    if not re.fullmatch(r"grundriss_[a-z]+\.(svg|png)", name):
        raise ValueError("Dateiname nicht erlaubt")
    os.makedirs(ZIEL, exist_ok=True)
    with open(os.path.join(ZIEL, name), "wb" if modus == "neu" else "ab") as f:
        f.write(base64.b64decode(teil))
    print("ok")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(f"Fehler: {fehler}")
