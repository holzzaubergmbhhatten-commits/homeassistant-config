#!/usr/bin/env python3
"""Helfer-Seite (www/helfer.html): Aufgaben für Oma & Opa mit Fotos zu jedem Schritt.

Aufgaben-Texte: claude_tools/helfer_vorlage.json (im Repository).
Fotos und „zuletzt erledigt“: lokal in Home Assistant (/config/www/helfer/, /config/helfer_daten.json).

Aufruf:
  helfer.py daten                                → JSON {aufgaben, fotos, zuletzt}
  helfer.py foto <b64 JSON {aufgabe, schritt, teil, letzt}> <Base64-Stück …>   (Foto in Stücken)
  helfer.py foto_weg <b64 JSON {aufgabe, schritt}>
  helfer.py erledigt <b64 JSON {aufgabe}>
"""
import base64
import io
import json
import os
import re
import sys
import uuid
from datetime import date

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, "helfer_vorlage.json")
DATEN = "/config/helfer_daten.json"
FOTOS = "/config/www/helfer"
TMP = "/config/.helfer_upload"


def lesen():
    try:
        with open(DATEN, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("fotos", {})
    d.setdefault("zuletzt", {})
    return d


def schreiben(d):
    tmp = DATEN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, DATEN)


def sicher(t):
    return re.sub(r"[^a-z0-9-]", "", str(t).lower())[:40]


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else "daten"
    auftrag = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8")) if len(sys.argv) > 2 and sys.argv[2] not in ("", "-") else {}
    d = lesen()
    if aktion == "daten":
        with open(VORLAGE, encoding="utf-8") as f:
            vorlage = json.load(f)
        print(json.dumps({"ok": True, "aufgaben": vorlage["aufgaben"], "fotos": d["fotos"], "zuletzt": d["zuletzt"]}, ensure_ascii=False))
        return
    aufgabe, schritt = sicher(auftrag.get("aufgabe", "")), int(auftrag.get("schritt") or 0)
    if not aufgabe:
        raise ValueError("Aufgabe fehlt")
    schluessel = f"{aufgabe}/{schritt}"
    if aktion == "foto":
        os.makedirs(TMP, exist_ok=True)
        teil_pfad = os.path.join(TMP, f"{aufgabe}-{schritt}.b64")
        stueck = "".join(sys.argv[3:])
        with open(teil_pfad, "w" if int(auftrag.get("teil") or 0) == 0 else "a", encoding="ascii") as f:
            f.write(stueck)
        if not auftrag.get("letzt"):
            print(json.dumps({"ok": True, "weiter": True}))
            return
        with open(teil_pfad, encoding="ascii") as f:
            roh = base64.b64decode(f.read())
        os.remove(teil_pfad)
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(roh))).convert("RGB")
        img.thumbnail((1400, 1400))
        os.makedirs(FOTOS, exist_ok=True)
        name = f"{aufgabe}-{schritt}-{uuid.uuid4().hex[:8]}.jpg"
        img.save(os.path.join(FOTOS, name), "JPEG", quality=80)
        alt = d["fotos"].get(schluessel)
        if alt and os.path.exists(os.path.join(FOTOS, alt)):
            os.remove(os.path.join(FOTOS, alt))
        d["fotos"][schluessel] = name
        schreiben(d)
        print(json.dumps({"ok": True, "foto": name}))
    elif aktion == "foto_weg":
        alt = d["fotos"].pop(schluessel, None)
        if alt and os.path.exists(os.path.join(FOTOS, alt)):
            os.remove(os.path.join(FOTOS, alt))
        schreiben(d)
        print(json.dumps({"ok": True}))
    elif aktion == "erledigt":
        d["zuletzt"][aufgabe] = date.today().isoformat()
        schreiben(d)
        print(json.dumps({"ok": True}))
    else:
        raise ValueError("unbekannte Aktion")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": str(fehler)[:200]}, ensure_ascii=False))
