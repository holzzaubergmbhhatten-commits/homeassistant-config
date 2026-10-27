#!/usr/bin/env python3
"""Rückblick von Viessmann für die Energie-Seite: Viessmann liefert bei manchen Werten (v. a. Wärmepumpe: Strom, Wärme)
die letzten Tage, Monate und Jahre als Liste mit. Die Integration in Home Assistant zeigt davon nur „heute/diesen Monat“.
Dieses Skript holt einmal am Tag alle Werte der Anlage und legt die Listen als Archiv ab (/config/viessmann_verlauf.json).
So gibt es Monate und Jahre schon vor der Einrichtung, und das Archiv wächst über die 13 Monate von Viessmann hinaus.

Anmeldung: nutzt nur den Zugang, den die Viessmann-Integration ohnehin hat (wird nur gelesen, nie erneuert oder
ausgegeben). Ist er gerade abgelaufen, wird es beim nächsten Mal versucht.

Aufruf: viessmann_verlauf.py holen | lesen   → JSON auf stdout"""
import datetime
import json
import sys
import time
import urllib.request

API = "https://api.viessmann-climatesolutions.com/iot/v2"
EINTRAEGE = "/config/.storage/core.config_entries"
ARCHIV = "/config/viessmann_verlauf.json"
EINHEIT = {"kilowattHour": ("kWh", 1), "wattHour": ("kWh", 0.001), "kWh": ("kWh", 1), "Wh": ("kWh", 0.001),
           "cubicMeter": ("m³", 1), "liter": ("l", 1)}


def zugang():
    with open(EINTRAEGE, encoding="utf-8") as f:
        eintraege = json.load(f)["data"]["entries"]
    for e in eintraege:
        if e.get("domain") == "vicare":
            token = (e.get("data") or {}).get("token") or {}
            if token.get("access_token") and token.get("expires_at", 0) > time.time() + 60:
                return token["access_token"]
            return None
    return None


def holen_url(pfad, token):
    req = urllib.request.Request(API + pfad, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def laden():
    try:
        with open(ARCHIV, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"archiv": {}, "stand": None}


def monat_minus(d, n):
    m = d.year * 12 + d.month - 1 - n
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


def eintragen(archiv, name, geraet, props):
    """Listen (day/week/month/year) und Summen (currentMonth, lastMonth …) eines Merkmals ins Archiv übernehmen."""
    heute = datetime.date.today()
    gelesen = (props.get("dayValueReadAt") or {}).get("value")
    try:
        bezug = datetime.date.fromisoformat(str(gelesen)[:10]) if gelesen else heute
    except ValueError:
        bezug = heute
    a = archiv.setdefault(name, {"geraet": geraet, "einheit": "", "tag": {}, "monat": {}, "jahr": {}})
    a["geraet"] = geraet

    def wert(p):
        einheit, faktor = EINHEIT.get(p.get("unit") or "", (p.get("unit") or "", 1))
        a["einheit"] = einheit or a.get("einheit", "")
        return faktor

    for schluessel, p in props.items():
        if not isinstance(p, dict):
            continue
        v = p.get("value")
        if isinstance(v, list) and schluessel in ("day", "month", "year"):
            faktor = wert(p)
            for i, x in enumerate(v):
                if not isinstance(x, (int, float)):
                    continue
                x = round(x * faktor, 3)
                if schluessel == "day":
                    a["tag"][(bezug - datetime.timedelta(days=i)).isoformat()] = x
                elif schluessel == "month":
                    a["monat"][monat_minus(bezug, i)] = x
                else:
                    a["jahr"][str(bezug.year - i)] = x
        elif isinstance(v, (int, float)) and schluessel in ("currentDay", "currentMonth", "lastMonth", "currentYear", "lastYear"):
            faktor = wert(p)
            x = round(v * faktor, 3)
            if schluessel == "currentDay":
                a["tag"][heute.isoformat()] = x
            elif schluessel == "currentMonth":
                a["monat"][monat_minus(heute, 0)] = x
            elif schluessel == "lastMonth":
                a["monat"][monat_minus(heute, 1)] = x
            elif schluessel == "currentYear":
                a["jahr"][str(heute.year)] = x
            else:
                a["jahr"][str(heute.year - 1)] = x
    if not (a["tag"] or a["monat"] or a["jahr"]):
        archiv.pop(name, None)
    else:
        a["tag"] = dict(sorted(a["tag"].items())[-400:])


def holen():
    token = zugang()
    if not token:
        return {"ok": False, "fehler": "Viessmann-Zugang gerade nicht gültig – wird später nochmal versucht"}
    daten = laden()
    archiv = daten.setdefault("archiv", {})
    anlagen = holen_url("/equipment/installations?includeGateways=true", token).get("data") or []
    abrufe = 0
    for anlage in anlagen:
        for gw in anlage.get("gateways") or []:
            for geraet in gw.get("devices") or []:
                if abrufe >= 6 or geraet.get("id") == "gateway":
                    continue
                abrufe += 1
                pfad = f"/features/installations/{anlage['id']}/gateways/{gw['serial']}/devices/{geraet['id']}/features"
                try:
                    merkmale = holen_url(pfad, token).get("data") or []
                except Exception:  # noqa: BLE001 – ein Gerät ohne Antwort soll die anderen nicht aufhalten
                    continue
                name = geraet.get("modelId") or geraet.get("deviceType") or geraet.get("id")
                for m in merkmale:
                    if m.get("isEnabled", True) and isinstance(m.get("properties"), dict):
                        eintragen(archiv, m.get("feature", ""), name, m["properties"])
    daten["stand"] = datetime.datetime.now().isoformat(timespec="minutes")
    with open(ARCHIV, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False)
    return {"ok": True, "stand": daten["stand"], "merkmale": len(archiv)}


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else "lesen"
    if aktion == "holen":
        print(json.dumps(holen(), ensure_ascii=False))
    else:
        d = laden()
        d["ok"] = True
        print(json.dumps(d, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": f"{type(fehler).__name__}: {str(fehler)[:200]}"}, ensure_ascii=False))
