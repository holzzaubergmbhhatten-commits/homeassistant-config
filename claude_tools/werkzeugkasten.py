#!/usr/bin/env python3
"""Werkzeugkasten (Seite „Links“, www/werkzeugkasten.html): Linkliste holen und lesen.

Die Liste steht im privaten Repository „webseiten“ (werkzeug/werkzeugkasten.json), weil manche Adressen nicht
öffentlich werden sollen – dieses Repository hier ist öffentlich. Home Assistant holt sie mit dem GitHub-Schlüssel
(input_text.github_handbuch_schluessel, trägt Marco ein) und legt sie lokal ab: /config/werkzeugkasten.json
(nicht unter www/, also nicht ohne Anmeldung abrufbar).

Aufruf: werkzeugkasten.py holen <base64(Schlüssel)>   → Liste aktualisieren
        werkzeugkasten.py lesen                       → Liste ausgeben
Ausgabe JSON: {"ok", "liste", "stand", "fehler"}"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

REPO = "holzzaubergmbhhatten-commits/webseiten"
PFAD = "werkzeug/werkzeugkasten.json"
LOKAL = "/config/werkzeugkasten.json"


def holen(schluessel):
    if len(schluessel) < 20:
        return {"ok": False, "fehler": "kein_schluessel"}
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/{PFAD}",
                                 headers={"Authorization": f"Bearer {schluessel}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "home-assistant-werkzeugkasten"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            daten = json.loads(base64.b64decode(json.load(r)["content"]).decode("utf-8"))
    except urllib.error.HTTPError as fehler:
        return {"ok": False, "fehler": "GitHub lehnt den Schlüssel ab" if fehler.code in (401, 403) else f"GitHub antwortet {fehler.code}"}
    tmp = LOKAL + ".tmp"
    json.dump(daten, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, LOKAL)
    return {"ok": True, "liste": daten, "stand": daten.get("stand", "")}


def lesen():
    try:
        daten = json.load(open(LOKAL, encoding="utf-8"))
        return {"ok": True, "liste": daten, "stand": daten.get("stand", "")}
    except (OSError, ValueError):
        return {"ok": False, "fehler": "noch_nicht_geholt"}


if __name__ == "__main__":
    try:
        if len(sys.argv) > 2 and sys.argv[1] == "holen":
            print(json.dumps(holen(base64.b64decode(sys.argv[2]).decode("utf-8").strip()), ensure_ascii=False))
        else:
            print(json.dumps(lesen(), ensure_ascii=False))
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": str(fehler)[:200]}, ensure_ascii=False))
