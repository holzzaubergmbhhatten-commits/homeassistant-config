#!/usr/bin/env python3
"""Sucht den Omada-Controller (OC200) im Heimnetz: fragt alle Adressen im eigenen /24-Netz auf https (443 und 8043)
nach /api/info – der Omada-Controller antwortet dort mit seiner Kennung (omadacId) und Version.
Ausgabe: {"ok": true, "gefunden": [{"url": "https://192.168.0.x", "version": "…"}]} – nur lesen, ändert nichts."""
import json
import socket
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def eigenes_netz():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip.rsplit(".", 1)[0]


KONTEXT = ssl.create_default_context()
KONTEXT.check_hostname = False
KONTEXT.verify_mode = ssl.CERT_NONE


def pruefen(url):
    try:
        with urllib.request.urlopen(url + "/api/info", timeout=2.5, context=KONTEXT) as r:
            d = json.loads(r.read(20000).decode("utf-8", "replace"))
        res = d.get("result") or {}
        if res.get("omadacId"):
            return {"url": url, "version": str(res.get("controllerVer") or "")}
    except Exception:  # noqa: BLE001
        return None
    return None


def main():
    netz = eigenes_netz()
    ziele = [f"https://{netz}.{i}" + (":8043" if port == 8043 else "") for i in range(1, 255) for port in (443, 8043)]
    with ThreadPoolExecutor(max_workers=64) as pool:
        treffer = [x for x in pool.map(pruefen, ziele) if x]
    print(json.dumps({"ok": True, "netz": netz + ".0/24", "gefunden": treffer}))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": str(fehler)[:200]}))
