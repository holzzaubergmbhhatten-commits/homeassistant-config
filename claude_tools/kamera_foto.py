#!/usr/bin/env python3
"""Aktuelles Einzelbild einer Kamera über go2rtc holen (gleiche Quelle wie das Livebild auf dem Monitor).

Aufruf: python3 kamera_foto.py <stream> <datei>
<stream> = go2rtc-Name, z. B. draussen_hot_tor_kamera (Entitäts-ID ohne "camera.") oder hoftor_klingel.
Schreibt die Datei NUR, wenn ein echtes JPEG-Bild ankommt (sonst bleibt sie unverändert/fehlt).
Ausgabe: "ok" oder eine kurze Fehlermeldung.
"""
import os
import re
import sys
import urllib.request

API = "http://127.0.0.1:1984/api/frame.jpeg?src="


def main():
    if len(sys.argv) != 3:
        return "Aufruf: kamera_foto.py <stream> <datei>"
    stream, datei = sys.argv[1], sys.argv[2]
    if not re.fullmatch(r"[a-z0-9_]+", stream):
        return "ungültiger Kameraname"
    if not re.fullmatch(r"/media/[a-z0-9_]+\.jpg", datei):
        return "ungültiger Dateiname"
    with urllib.request.urlopen(API + stream, timeout=20) as r:
        daten = r.read()
    if len(daten) < 5000 or not daten.startswith(b"\xff\xd8"):
        return f"kein Bild ({len(daten)} Bytes)"
    tmp = datei + ".tmp"
    with open(tmp, "wb") as f:
        f.write(daten)
    os.replace(tmp, datei)
    return "ok"


if __name__ == "__main__":
    try:
        print(main())
    except Exception as fehler:  # noqa: BLE001
        print(f"Fehler: {type(fehler).__name__}: {fehler}"[:200])
