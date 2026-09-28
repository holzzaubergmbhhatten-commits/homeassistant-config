#!/usr/bin/env python3
"""Kurzer Selbsttest der Live-Kameras (go2rtc). Gibt einen Bericht ohne Passwörter aus."""
import json
import os
import urllib.request

API = "http://127.0.0.1:1984"
zeilen = []
cfg = {}

try:
    with open("/config/go2rtc.yaml", encoding="utf-8") as f:
        cfg = json.load(f)
    zeilen.append("go2rtc.yaml: " + (", ".join(cfg.get("streams", {})) or "KEINE Kameras"))
except Exception as e:  # noqa: BLE001
    zeilen.append(f"go2rtc.yaml fehlt/kaputt: {e}")

if not cfg.get("streams"):
    try:
        with open("/config/.storage/core.config_entries", encoding="utf-8") as f:
            eintraege = json.load(f)["data"]["entries"]
        for e in eintraege:
            if e["domain"] == "generic":
                o = {**e.get("data", {}), **e.get("options", {})}
                q = str(o.get("stream_source") or "")
                zeilen.append(f"generic '{e['title']}': Felder {sorted(o)}; Quelle beginnt mit {q[:7]!r}")
    except Exception as e:  # noqa: BLE001
        zeilen.append(f"config_entries: {e}")

try:
    with urllib.request.urlopen(API + "/api/streams", timeout=5) as r:
        streams = json.load(r)
    zeilen.append("go2rtc läuft, kennt: " + (", ".join(streams) or "nichts"))
except Exception as e:  # noqa: BLE001
    streams = {}
    zeilen.append(f"go2rtc nicht erreichbar: {e}")

for name in [n for n in streams if not n.endswith("_hd")][:1]:
    for art in ("frame.jpeg", "stream.mjpeg"):
        try:
            with urllib.request.urlopen(f"{API}/api/{art}?src={name}", timeout=20) as r:
                daten = r.read(200000 if art == "stream.mjpeg" else None)
            zeilen.append(f"{name} {art}: OK ({len(daten)} Bytes)")
        except Exception as e:  # noqa: BLE001
            zeilen.append(f"{name} {art}: FEHLER {e}")

print("\n".join(zeilen)[:3500])
