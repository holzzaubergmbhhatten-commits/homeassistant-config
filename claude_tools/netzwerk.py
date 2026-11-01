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


def poe_port(name):
    """Welcher Switch-Port versorgt das Gerät „name“ (z. B. Access Point „Hoftor“) mit Strom? Aus den Port-Beschriftungen.
    Nur Ports, deren Beschriftung „Access Point“ oder „Kamera“ enthält (keine Zuleitungen zu weiteren Geräten)."""
    import re
    try:
        daten = json.load(open(DATEN, encoding="utf-8"))
    except (OSError, ValueError):
        daten = {}
    geraet = re.sub(r"[^a-zäöüß0-9]+", " ", name.lower())
    treffer = []
    for schluessel, b in (daten.get("ports") or {}).items():
        text = f"{b.get('name', '')} {b.get('dose', '')}".lower()
        if not re.search(r"access ?point|kamera", text):
            continue
        rest = re.sub(r"access ?point|kamera|dose|raum", " ", text)
        woerter = [w for w in re.split(r"[^a-zäöüß0-9]+", rest) if len(w) >= 3]
        if woerter and any(re.search(r"\b" + re.escape(w), geraet) for w in woerter):
            dev, port = schluessel.split("|", 1)
            treffer.append({"geraet": dev, "port": int(port)})
    print(json.dumps({"ok": True, "ports": treffer}, ensure_ascii=False))


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "poe_port":   # Argument: base64(JSON-Liste mit Gerätenamen)
        import contextlib
        import io
        alle = {}
        for name in json.loads(base64.b64decode(sys.argv[2]).decode("utf-8")):
            puffer = io.StringIO()
            with contextlib.redirect_stdout(puffer):
                poe_port(name)
            alle[name] = json.loads(puffer.getvalue())["ports"]
        print(json.dumps({"ok": True, "ports": alle}, ensure_ascii=False))
        return
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
