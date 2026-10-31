#!/usr/bin/env python3
"""Fristen aus der Akte für die Morgen-Nachricht (packages/tagesbrief.yaml): was in den nächsten 7 Tagen fällig ist.
Liest /config/akte.json nur. Ausgabe: {"fristen": [{"datum", "tag", "was", "titel"}]}"""
import json
from datetime import date, datetime, timedelta

TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def main():
    try:
        with open("/config/akte.json", encoding="utf-8") as f:
            liste = json.load(f)
    except (OSError, ValueError):
        liste = []
    heute = date.today()
    aus = []
    for e in liste if isinstance(liste, list) else []:
        if not isinstance(e, dict) or e.get("geloescht"):
            continue
        for fr in e.get("fristen") or []:
            try:
                d = datetime.strptime(fr["datum"], "%Y-%m-%d").date()
            except (KeyError, ValueError, TypeError):
                continue
            if heute <= d <= heute + timedelta(days=7):
                aus.append({"datum": d.isoformat(), "tag": "heute" if d == heute else f"{TAGE[d.weekday()]} {d.strftime('%d.%m.')}",
                            "was": str(fr.get("was", ""))[:80], "titel": str(e.get("titel") or e.get("absender") or "")[:60]})
    aus.sort(key=lambda x: x["datum"])
    print(json.dumps({"fristen": aus[:6]}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 – die Morgen-Nachricht kommt dann eben ohne Fristen
        print('{"fristen": []}')
