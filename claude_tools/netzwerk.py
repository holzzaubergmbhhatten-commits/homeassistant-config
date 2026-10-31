#!/usr/bin/env python3
"""Netzwerk-Seite (www/netzwerk.html): eigene Beschriftungen der Switch-Ports und Access Points speichern.
Aufruf: netzwerk.py speichern <base64-Stücke>   → /config/www/netzwerk_daten.json (lokal, nicht im Repository)
Format: {"ports": {"<device_id>|<port>": {"name": "…", "dose": "…", "notiz": "…"}}, "geraete": {"<device_id>": {"ort": "…"}}}
Keine IP- oder MAC-Adressen speichern – die Seite zeigt sie nicht an.
"""
import base64
import json
import os
import sys

DATEN = "/config/www/netzwerk_daten.json"


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "speichern":
        raise ValueError("unbekannte Aktion")
    neu = json.loads(base64.b64decode("".join(sys.argv[2:])).decode("utf-8"))
    if not isinstance(neu, dict) or not isinstance(neu.get("ports", {}), dict):
        raise ValueError("unerwartetes Format")
    tmp = DATEN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"ports": neu.get("ports") or {}, "geraete": neu.get("geraete") or {},
                   "vorbelegt": int(neu.get("vorbelegt") or 0)}, f, ensure_ascii=False)
    os.replace(tmp, DATEN)
    print(json.dumps({"ok": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": str(fehler)[:200]}, ensure_ascii=False))
