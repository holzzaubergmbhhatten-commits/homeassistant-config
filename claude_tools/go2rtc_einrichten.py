#!/usr/bin/env python3
"""Kamera-Liste für go2rtc aus den Home-Assistant-Kameras erzeugen.

Liest die per Oberfläche angelegten "Generic Camera"-Kameras (Tapo, RTSP) aus
/config/.storage und schreibt /config/go2rtc.yaml. Die Datei bleibt lokal (nicht im
Repository), denn sie enthält die Kamera-Passwörter.

Stream-Namen = Entitäts-ID ohne "camera.", z. B. draussen_hof_hinten.
Zusätzlich "<name>_hd" mit dem Hauptstream (stream1) für die Großansicht.

Die go2rtc-Oberfläche ist nur vom Monitor selbst (localhost) ohne Passwort erreichbar;
von anderen Geräten im Netz (z. B. Gäste im WLAN) nur mit dem Zufallspasswort in der Datei.

Ausgabe: "geändert" oder "unverändert" (dann muss go2rtc nicht neu starten).
"""
import json
import os
import re
import secrets
import sys
import urllib.parse

ZIEL = "/config/go2rtc.yaml"
STORAGE = "/config/.storage"


def lade(name):
    with open(os.path.join(STORAGE, name), encoding="utf-8") as f:
        return json.load(f)["data"]


def mit_zugang(url, benutzer, passwort):
    teile = urllib.parse.urlsplit(url)
    if not benutzer or "@" in teile.netloc:
        return url
    zugang = urllib.parse.quote(benutzer, safe="") + ":" + urllib.parse.quote(passwort or "", safe="")
    return urllib.parse.urlunsplit(teile._replace(netloc=f"{zugang}@{teile.netloc}"))


def main():
    eintraege = [e for e in lade("core.config_entries")["entries"]
                 if e["domain"] == "generic" and not e.get("disabled_by")]
    entitaeten = {e["config_entry_id"]: e["entity_id"] for e in lade("core.entity_registry")["entities"]
                  if e["entity_id"].startswith("camera.")}

    streams = {}
    for e in eintraege:
        o = {**e.get("data", {}), **e.get("options", {})}
        quelle = (o.get("stream_source") or "").strip()
        if not quelle.startswith("rtsp") or "{{" in quelle:
            continue
        name = entitaeten.get(e["entry_id"], "camera." + re.sub(r"\W+", "_", e["title"].lower())).split(".", 1)[1]
        url = mit_zugang(quelle, o.get("username"), o.get("password"))
        # Zweite Quelle: Umwandlung nach MJPEG (das kann der Browser auf dem Monitor anzeigen),
        # per Prozessor (Grafikkarte klappt auf diesem Mini-PC nicht) – läuft nur, wenn jemand zuschaut
        streams[name] = [url, f"ffmpeg:{name}#video=mjpeg"]
        if re.search(r"/stream2$", url):
            streams[name + "_hd"] = [re.sub(r"/stream2$", "/stream1", url),
                                     f"ffmpeg:{name}_hd#video=mjpeg#width=1920"]

    alt = {}
    if os.path.exists(ZIEL):
        try:
            with open(ZIEL, encoding="utf-8") as f:
                inhalt = f.read()
            try:
                import yaml  # go2rtc schreibt die Datei als YAML, wenn man dort etwas hinzufügt
                alt = yaml.safe_load(inhalt) or {}
            except ImportError:
                alt = json.loads(inhalt)
        except ValueError:
            alt = {}
    passwort = (alt.get("api") or {}).get("password") or secrets.token_urlsafe(12)
    if len(sys.argv) > 1 and sys.argv[1] == "--passwort":
        print(passwort)
        return

    # Ring-Klingel: in der go2rtc-Oberfläche per Ring-Login hinzugefügte Streams behalten und
    # unter dem festen Namen "hoftor_klingel" (mit MJPEG für den Monitor) bereitstellen
    for name, quelle in (alt.get("streams") or {}).items():
        quellen = quelle if isinstance(quelle, list) else [quelle]
        if any("ring:" in str(q) for q in quellen) and name not in streams:
            streams[name] = quelle
    ring = next((str(q) for quelle in streams.values()
                 for q in (quelle if isinstance(quelle, list) else [quelle])
                 if str(q).startswith("ring:") and "snapshot" not in str(q)), None)
    if ring:
        streams["hoftor_klingel"] = [ring, "ffmpeg:hoftor_klingel#video=mjpeg"]

    neu = {
        "api": {"listen": ":1984", "username": "zuhause", "password": passwort},
        "rtsp": {"listen": "127.0.0.1:8554"},
        "streams": streams,
    }
    if neu == alt:
        print("unverändert")
        return
    with open(ZIEL, "w", encoding="utf-8") as f:
        json.dump(neu, f, indent=2)
    print("geändert")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:
        print(f"Fehler: {fehler}")
