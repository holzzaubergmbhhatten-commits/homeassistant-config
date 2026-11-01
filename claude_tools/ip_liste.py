#!/usr/bin/env python3
"""Welche Geräte spricht Home Assistant über eine feste Adresse (IP) an?
Liest /config/.storage/core.config_entries (nur lesen) und /config/go2rtc.yaml und listet je Integration
Name + Adresse. Diese Geräte sollten im Router (Omada → Clients → „Feste IP-Adresse verwenden“) eine feste Adresse
bekommen – sonst sind sie nach einem Router-Neustart evtl. „nicht erreichbar“.
Passwörter werden nie ausgegeben. Ausgabe: JSON {"ok": true, "geraete": [{"art", "name", "adresse"}]}"""
import json
import os
import re
import sys

MARKE = "/config/.ip_liste_gesendet"

IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SCHLUESSEL = ("host", "ip_address", "ip", "url", "stream_source", "still_image_url", "address", "base_url", "server")


def main():
    if "einmal" in sys.argv[1:] and os.path.exists(MARKE):
        print(json.dumps({"ok": True, "schon": True, "geraete": []}))
        return
    with open("/config/.storage/core.config_entries", encoding="utf-8") as f:
        eintraege = json.load(f)["data"]["entries"]
    liste, gesehen = [], set()
    for e in eintraege:
        if e.get("disabled_by"):
            continue
        werte = {**e.get("data", {}), **e.get("options", {})}
        for k in SCHLUESSEL:
            v = werte.get(k)
            if not isinstance(v, str):
                continue
            for ip in IP.findall(v):
                if ip.startswith("127.") or ip == "0.0.0.0":
                    continue
                kennung = (e["domain"], e.get("title"), ip)
                if kennung in gesehen:
                    continue
                gesehen.add(kennung)
                liste.append({"art": e["domain"], "name": e.get("title") or e["domain"], "adresse": ip})
    try:
        text = open("/config/go2rtc.yaml", encoding="utf-8").read()
        for name, ip in re.findall(r"^\s{2}(\w+):\s*\n\s*-\s*\w+://[^\n]*?@?((?:\d{1,3}\.){3}\d{1,3})", text, re.M):
            kennung = ("go2rtc", name, ip)
            if kennung not in gesehen and not name.endswith("_hd"):
                gesehen.add(kennung)
                liste.append({"art": "kamera (go2rtc)", "name": name, "adresse": ip})
    except OSError:
        pass
    liste.sort(key=lambda x: tuple(int(t) for t in x["adresse"].split(".")))
    if "einmal" in sys.argv[1:]:
        open(MARKE, "w").close()
    print(json.dumps({"ok": True, "geraete": liste}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": str(fehler)[:200]}))
