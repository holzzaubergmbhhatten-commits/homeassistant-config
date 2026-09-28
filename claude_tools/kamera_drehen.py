#!/usr/bin/env python3
"""Tapo-Kamera schwenken/neigen über ONVIF (Port 2020), ohne Zusatz-Integration.

Aufruf: python3 kamera_drehen.py <kamera> <links|rechts|hoch|runter>
<kamera> = Entitäts-ID ohne "camera.", z. B. draussen_hof_hinten.
Zugangsdaten kommen aus der "Generic Camera"-Einrichtung in Home Assistant.
Ausgabe: "ok" oder eine Fehlermeldung (für die Benachrichtigung).
"""
import base64
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

STORAGE = "/config/.storage"
RICHTUNG = {"links": (-0.5, 0), "rechts": (0.5, 0), "hoch": (0, 0.5), "runter": (0, -0.5)}
DAUER = 0.6  # Sekunden Bewegung pro Knopfdruck


def lade(name):
    with open(os.path.join(STORAGE, name), encoding="utf-8") as f:
        return json.load(f)["data"]


def zugang(kamera):
    entitaeten = {e["entity_id"]: e["config_entry_id"] for e in lade("core.entity_registry")["entities"]}
    eintrag_id = entitaeten.get("camera." + kamera)
    for e in lade("core.config_entries")["entries"]:
        if e["entry_id"] == eintrag_id:
            o = {**e.get("data", {}), **e.get("options", {})}
            teile = urllib.parse.urlsplit(o.get("stream_source") or "")
            benutzer = o.get("username") or urllib.parse.unquote(teile.username or "")
            passwort = o.get("password") or urllib.parse.unquote(teile.password or "")
            return teile.hostname, benutzer, passwort
    raise RuntimeError(f"Kamera {kamera} nicht gefunden")


def soap(host, benutzer, passwort, body):
    nonce = os.urandom(16)
    erstellt = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    digest = base64.b64encode(hashlib.sha1(nonce + erstellt.encode() + passwort.encode()).digest()).decode()
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Header>
<Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
<UsernameToken><Username>{benutzer}</Username>
<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</Password>
<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{base64.b64encode(nonce).decode()}</Nonce>
<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">{erstellt}</Created>
</UsernameToken></Security></s:Header><s:Body>{body}</s:Body></s:Envelope>"""
    anfrage = urllib.request.Request(f"http://{host}:2020/onvif/service", data=xml.encode(),
                                     headers={"Content-Type": "application/soap+xml; charset=utf-8"})
    try:
        with urllib.request.urlopen(anfrage, timeout=6) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        grund = re.search(r"<[^>]*Text[^>]*>([^<]+)<", e.read().decode("utf-8", "replace"))
        raise RuntimeError(f"HTTP {e.code} {grund.group(1) if grund else ''}".strip())


def main():
    kamera, richtung = sys.argv[1], sys.argv[2]
    x, y = RICHTUNG[richtung]
    host, benutzer, passwort = zugang(kamera)
    profile = soap(host, benutzer, passwort, '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>')
    token = re.search(r'Profiles[^>]*token="([^"]+)"', profile)
    if not token:
        raise RuntimeError("kein ONVIF-Profil gefunden")
    t = token.group(1)
    soap(host, benutzer, passwort,
         f'<ContinuousMove xmlns="http://www.onvif.org/ver20/ptz/wsdl"><ProfileToken>{t}</ProfileToken>'
         f'<Velocity><PanTilt x="{x}" y="{y}" xmlns="http://www.onvif.org/ver10/schema"/></Velocity></ContinuousMove>')
    time.sleep(DAUER)
    soap(host, benutzer, passwort,
         f'<Stop xmlns="http://www.onvif.org/ver20/ptz/wsdl"><ProfileToken>{t}</ProfileToken>'
         '<PanTilt>true</PanTilt><Zoom>false</Zoom></Stop>')
    print("ok")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(f"Fehler: {fehler}")
