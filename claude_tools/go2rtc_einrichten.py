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
        # mit Grafikkarte, falls vorhanden – go2rtc startet sie nur, wenn jemand zuschaut
        streams[name] = [url, f"ffmpeg:{name}#video=mjpeg#hardware"]
        if re.search(r"/stream2$", url):
            streams[name + "_hd"] = [re.sub(r"/stream2$", "/stream1", url),
                                     f"ffmpeg:{name}_hd#video=mjpeg#hardware"]

    alt = {}
    if os.path.exists(ZIEL):
        try:
            with open(ZIEL, encoding="utf-8") as f:
                alt = json.load(f)
        except ValueError:
            alt = {}
    passwort = (alt.get("api") or {}).get("password") or secrets.token_urlsafe(12)

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
