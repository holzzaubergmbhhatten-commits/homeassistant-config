"""Finanzen-Seite (www/finanzen.html): Haushaltsplan (Einnahmen/Ausgaben) und Vorsorge-Einstellungen.
Daten: /config/finanzen.json – nur lokal auf dem Home-Assistant-Rechner, nie im Repository.
In dieser Datei stehen bewusst KEINE Beträge (das Repository ist öffentlich).
Aufruf über script.akte_aktion mit was = fi_lesen / fi_speichern (text = JSON)."""
import json
from datetime import datetime

import akte

DATEI = "/config/finanzen.json"
RHYTHMUS = ("monat", "quartal", "halbjahr", "jahr")


def _zahl(x):
    try:
        return round(float(str(x).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return 0.0


def _posten(p):
    return {
        "name": str(p.get("name") or "")[:80],
        "betrag": _zahl(p.get("betrag")),
        "rhythmus": p.get("rhythmus") if p.get("rhythmus") in RHYTHMUS else "monat",
        "art": "ein" if p.get("art") == "ein" else "aus",
        "gruppe": str(p.get("gruppe") or "")[:40],
        "notiz": str(p.get("notiz") or "")[:200],
    }


def seite(auftrag):
    was = auftrag.get("was")
    d = akte.json_laden(DATEI, None) or {"posten": [], "vorsorge": {}, "geaendert": ""}
    if was == "fi_speichern":
        try:
            neu = json.loads(auftrag.get("text") or "{}")
        except ValueError:
            return {"ok": False, "fehler": "ungültig"}
        if isinstance(neu.get("posten"), list):
            d["posten"] = [_posten(p) for p in neu["posten"][:300]
                           if isinstance(p, dict) and (p.get("name") or p.get("betrag"))]
        if isinstance(neu.get("vorsorge"), dict):
            d["vorsorge"] = {k: v for k, v in neu["vorsorge"].items() if isinstance(v, (int, float, str, bool))}
        d["geaendert"] = datetime.now().strftime("%d.%m.%Y %H:%M") + (" · " + str(auftrag.get("wer")) if auftrag.get("wer") else "")
        akte.json_schreiben(DATEI, d)
    return {"ok": True, "daten": d}
