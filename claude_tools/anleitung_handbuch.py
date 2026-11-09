#!/usr/bin/env python3
"""Anleitung aus der Akte ins Haus-Handbuch bringen (Knopf „📖 Ja, ins Haus-Handbuch“ in Telegram).

Lädt die PDF über die GitHub-Schnittstelle in das (private) Repository der Webseiten. Dort lädt der Ablauf
„Hochladen“ sie auf den Server, und „Anleitungen holen“ trägt sie in die Liste des Handbuchs ein.
Den Zielordner im Repository liest das Programm aus werkzeug/handbuch_ziel.json im privaten Repository –
er steht absichtlich nicht hier (dieses Repository ist öffentlich).

Aufruf: anleitung_handbuch.py <base64(JSON {"id": Akte-Eintrag, "schluessel": GitHub-Schlüssel, "von": Name})>
Ausgabe JSON: {"ok", "name", "geraet", "neu", "fehler"}"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

REPO = "holzzaubergmbhhatten-commits/webseiten"
QUELLEN = "werkzeug/anleitungen_quellen.json"
ZIEL = "werkzeug/handbuch_ziel.json"
AKTE = "/config/akte.json"
ABLAGE = "/config/akte_ablage/"


def gh(methode, pfad, schluessel, daten=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/{pfad}", method=methode,
                                 data=json.dumps(daten).encode() if daten is not None else None,
                                 headers={"Authorization": f"Bearer {schluessel}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "home-assistant-handbuch", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as fehler:
        if fehler.code == 404 and methode == "GET":
            return None
        if fehler.code in (401, 403):
            raise RuntimeError("GitHub lehnt den Schlüssel ab (abgelaufen oder ohne Schreibrecht auf „webseiten“)")
        raise RuntimeError(f"GitHub antwortet {fehler.code}")


def flach(t):
    return re.sub(r"[\s\-/._]", "", str(t)).lower()


def main():
    auftrag = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
    schluessel = (auftrag.get("schluessel") or "").strip()
    if len(schluessel) < 20:
        print(json.dumps({"ok": False, "fehler": "kein_schluessel"}))
        return
    akte = json.load(open(AKTE, encoding="utf-8"))
    kennung = auftrag.get("id")
    e = next((x for x in akte if isinstance(x, dict) and x.get("id") == kennung), None)
    if not e:   # Seite/Teil wurde inzwischen mit anderen zu einem Dokument zusammengefügt → das ganze Dokument nehmen
        e = next((x for x in akte if isinstance(x, dict) and kennung in (x.get("aufgegangen") or [])), None)
    if not e:
        raise RuntimeError("Dokument in der Akte nicht gefunden (wurde es gelöscht?)")
    if not str(e.get("datei", "")).lower().endswith(".pdf"):
        raise RuntimeError("Das Dokument ist kein PDF")
    pfad = os.path.join(ABLAGE, e["datei"])
    if os.path.getsize(pfad) > 45_000_000:
        raise RuntimeError("PDF ist größer als 45 MB")

    ziel = gh("GET", ZIEL, schluessel)
    if not ziel:
        raise RuntimeError(f"{ZIEL} fehlt im Repository")
    ordner = json.loads(base64.b64decode(ziel["content"]))["ordner"].strip("/")

    q = gh("GET", QUELLEN, schluessel)
    quellen = json.loads(base64.b64decode(q["content"]).decode("utf-8"))
    text = flach(" ".join(str(e.get(k) or "") for k in ("titel", "absender")) + " " + " ".join(e.get("schlagworte") or [])
                 + " " + (e.get("inhalt") or "")[:6000])
    beste, laenge = None, 0
    for g in quellen["geraete"]:
        for p in g.get("pruef", []):
            if len(flach(p)) >= 4 and flach(p) in text and len(flach(p)) > laenge:
                beste, laenge = g, len(flach(p))
    neu = beste is None
    if neu:
        kennung = re.sub(r"[^a-z0-9]+", "-", (e.get("titel") or "anleitung").lower().replace("ä", "ae").replace("ö", "oe")
                         .replace("ü", "ue").replace("ß", "ss")).strip("-")[:40] or "anleitung"
        while any(g["id"] == kennung for g in quellen["geraete"]):
            kennung += "-2"
        beste = {"id": kennung, "gruppe": "Sonstiges", "name": e.get("titel") or "Anleitung", "pruef": [], "hersteller": [], "suche": []}
        quellen["geraete"].append(beste)
    if any(g.get("akte_id") == e["id"] for g in quellen["geraete"]):   # dasselbe Dokument schon übernommen (z. B. Knopf bei jeder Seite)
        print(json.dumps({"ok": True, "name": next(g["name"] for g in quellen["geraete"] if g.get("akte_id") == e["id"]),
                          "geraet": beste["id"], "neu": False, "schon": True}, ensure_ascii=False))
        return
    beste["akte_id"] = e["id"]
    beste["manuell"] = {"quelle": f"{e.get('absender') or 'Hersteller'} – per Telegram von {auftrag.get('von') or 'Marco'}", "deutsch": True}

    datei_pfad = f"{ordner}/{beste['id']}.pdf"
    alt = gh("GET", datei_pfad, schluessel)
    with open(pfad, "rb") as f:
        inhalt = base64.b64encode(f.read()).decode()
    gh("PUT", datei_pfad, schluessel, {"message": f"Haus-Handbuch: Anleitung {beste['name']} (per Telegram)", "content": inhalt,
                                       **({"sha": alt["sha"]} if alt else {})})
    gh("PUT", QUELLEN, schluessel, {"message": f"Anleitungen: {beste['name']} von Hand hinterlegt",
                                    "content": base64.b64encode(json.dumps(quellen, ensure_ascii=False, indent=1).encode()).decode(),
                                    "sha": q["sha"]})
    print(json.dumps({"ok": True, "name": beste["name"], "geraet": beste["id"], "neu": neu}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": str(fehler)[:200]}, ensure_ascii=False))
