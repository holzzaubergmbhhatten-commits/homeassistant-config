#!/usr/bin/env python3
"""Seit wann steht eine Aufgabe auf der Liste? (Aufruf aus dem Template-Sensor "Aufgaben Liste", packages/aufgaben.yaml)

Liest die Dateien der lokalen To-do-Listen (/config/.storage/local_todo.*.ics) und gibt für jede Aufgabe
das Anlege-Datum aus (CREATED, sonst DTSTAMP). Ausgabe JSON: {"<uid>": "JJJJ-MM-TT", ...}.
"""
import glob
import json


def zeilen(text):
    """ICS-Zeilen mit Fortsetzungen (beginnen mit Leerzeichen) wieder zusammensetzen."""
    aus = []
    for z in text.splitlines():
        if z[:1] in (" ", "\t") and aus:
            aus[-1] += z[1:]
        else:
            aus.append(z)
    return aus


def datum(wert):
    w = wert.split(":")[-1].strip()
    return f"{w[0:4]}-{w[4:6]}-{w[6:8]}" if len(w) >= 8 and w[:8].isdigit() else ""


def main():
    seit = {}
    for pfad in glob.glob("/config/.storage/local_todo.*.ics"):
        try:
            with open(pfad, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        uid, erstellt, stempel, drin = "", "", "", False
        for z in zeilen(text):
            if z.startswith("BEGIN:VTODO"):
                uid, erstellt, stempel, drin = "", "", "", True
            elif z.startswith("END:VTODO") and drin:
                if uid and (erstellt or stempel):
                    seit[uid] = erstellt or stempel
                drin = False
            elif drin and z.startswith("UID"):
                uid = z.split(":", 1)[-1].strip()
            elif drin and z.startswith("CREATED"):
                erstellt = datum(z)
            elif drin and z.startswith("DTSTAMP"):
                stempel = datum(z)
    print(json.dumps(seit))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        print("{}")
