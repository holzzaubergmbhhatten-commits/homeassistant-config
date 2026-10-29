#!/usr/bin/env python3
"""Rückblick von Viessmann für die Energie-Seite: Viessmann liefert bei manchen Werten (v. a. Wärmepumpe: Strom, Wärme)
die letzten Tage, Monate und Jahre als Liste mit. Die Integration in Home Assistant zeigt davon nur „heute/diesen Monat“.
Dieses Skript holt einmal am Tag alle Werte der Anlage und legt die Listen als Archiv ab (/config/viessmann_verlauf.json).
So gibt es Monate und Jahre schon vor der Einrichtung, und das Archiv wächst über die 13 Monate von Viessmann hinaus.

Anmeldung: nutzt nur den Zugang, den die Viessmann-Integration ohnehin hat (wird nur gelesen, nie erneuert oder
ausgegeben). Ist er gerade abgelaufen, wird es beim nächsten Mal versucht.

Dazu kommen eingelesene Exporte aus dem Viessmann-Energieportal (gridX, CSV): Monats- und Tageswerte für PV, Netz,
Speicher, Wärmepumpe und Haushalt (/config/energie_historie.json, nur lokal). Die Energie-Seite liest die CSV, schickt
die Werte als JSON (base64, in Stücken) und zeigt sie dort, wo Home Assistant selbst noch nichts aufgezeichnet hat.

Exporte, die schon in der Akte oder im Eingang liegen (CSV mit „measuredAt“), werden beim Lesen von selbst übernommen.

Aufruf: viessmann_verlauf.py holen | lesen | import <base64-Stücke …>   → JSON auf stdout"""
import base64
import datetime
import json
import os
import sys
import time
import urllib.request

API = "https://api.viessmann-climatesolutions.com/iot/v2"
EINTRAEGE = "/config/.storage/core.config_entries"
ARCHIV = "/config/viessmann_verlauf.json"
HISTORIE = "/config/energie_historie.json"
FELDER = ("pv", "bezug", "einsp", "laden", "entladen", "wp", "haus")
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
    abrufe, geraete = 0, []
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
                geraete.append(f"{name}: {len(merkmale)} Werte")
                for m in merkmale:
                    if m.get("isEnabled", True) and isinstance(m.get("properties"), dict):
                        eintragen(archiv, m.get("feature", ""), name, m["properties"])
    daten["stand"] = datetime.datetime.now().isoformat(timespec="minutes")
    daten["geraete"] = geraete
    with open(ARCHIV, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False)
    return {"ok": True, "stand": daten["stand"], "merkmale": len(archiv)}


def historie_laden():
    try:
        with open(HISTORIE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"monat": {}, "tag": {}}


SUCHORTE = ("/config/akte_ablage", "/media/Akte-Eingang", "/media/akte", "/media/eingang", "/share")
SPALTEN = (("einsp", "einspeis"), ("bezug", "bezug"), ("wp", "rmepumpe"), ("pv", "pv"), ("haus", "haushalt"),
           ("entladen", "entladung"), ("laden", "batterieladung"))


def csv_lesen(text):
    """Export aus dem Viessmann-Energieportal (gridX) → {monat: {JJJJ-MM: {…}}, tag: {…}} in kWh, Zeit in deutscher Zeit."""
    import csv
    from zoneinfo import ZoneInfo
    zeilen = [z for z in csv.reader(text.splitlines()) if z]
    kopf = [k.lower() for k in zeilen[0]]
    if not kopf or "measuredat" not in kopf[0]:
        return None
    sp = {}
    for feld, wort in SPALTEN:
        i = next((i for i, k in enumerate(kopf) if wort in k and i not in sp.values()), None)
        if i is not None:
            sp[feld] = i
    werte = []
    for z in zeilen[1:]:
        try:
            t = datetime.datetime.fromisoformat(z[0].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Berlin"))
        except (ValueError, IndexError):
            continue
        w = {}
        for feld, i in sp.items():
            roh = (z[i] if i < len(z) else "").strip()
            if roh:
                faktor = 1 if "(kwh)" in kopf[i] else 0.001
                w[feld] = float(roh.replace(".", "").replace(",", ".") if "," in roh else roh) * faktor
        if w:
            werte.append((t, w))
    if not werte:
        return {"monat": {}, "tag": {}}
    schritt = (werte[1][0] - werte[0][0]).total_seconds() / 3600 if len(werte) > 1 else 24 * 30
    art = "monat" if schritt >= 24 * 27 else "tag"
    erg = {"monat": {}, "tag": {}}
    for t, w in werte:
        k = t.strftime("%Y-%m") if art == "monat" else t.strftime("%Y-%m-%d")
        ziel = erg[art].setdefault(k, {})
        for f, v in w.items():
            ziel[f] = ziel.get(f, 0) + v
    if art == "tag":
        for k, w in erg["tag"].items():
            z = erg["monat"].setdefault(k[:7], {})
            for f, v in w.items():
                z[f] = z.get(f, 0) + v
    return erg


def akte_durchsuchen():
    """CSV-Exporte, die in Akte, Eingang oder Medien liegen, einmal übernehmen (gemerkt an Pfad und Änderungszeit)."""
    h = historie_laden()
    bekannt = h.setdefault("dateien", {})
    neu = 0
    for ort in SUCHORTE:
        for wurzel, _ordner, dateien in os.walk(ort):
            if wurzel.count("/") - ort.count("/") > 4:
                continue
            for name in dateien:
                pfad = os.path.join(wurzel, name)
                if not name.lower().endswith((".csv", ".txt")):
                    continue
                try:
                    st = os.stat(pfad)
                    if st.st_size > 3_000_000 or bekannt.get(pfad) == st.st_mtime:
                        continue
                    with open(pfad, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                    erg = csv_lesen(text[text.find("measuredAt"):] if "measuredAt" in text else "")
                except (OSError, ValueError):
                    continue
                bekannt[pfad] = st.st_mtime
                if erg:
                    _uebernehmen(h, erg)
                    neu += 1
    if neu or bekannt:
        _speichern(h)
    return neu


def _uebernehmen(h, neu):
    zahl = 0
    for art in ("monat", "tag"):
        for k, werte in (neu.get(art) or {}).items():
            if not isinstance(werte, dict):
                continue
            sauber = {f: round(float(werte[f]), 3) for f in FELDER if isinstance(werte.get(f), (int, float))}
            if sauber:
                h.setdefault(art, {})[str(k)[:10]] = sauber
                zahl += 1
    return zahl


def _speichern(h):
    h["tag"] = dict(sorted(h.get("tag", {}).items())[-1500:])
    h["stand"] = datetime.datetime.now().isoformat(timespec="minutes")
    with open(HISTORIE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False)


def importieren(stuecke):
    neu = json.loads(base64.b64decode("".join(stuecke)).decode("utf-8"))
    h = historie_laden()
    zahl = 0
    for art in ("monat", "tag"):
        for k, werte in (neu.get(art) or {}).items():
            if not isinstance(werte, dict):
                continue
            sauber = {f: round(float(werte[f]), 3) for f in FELDER if isinstance(werte.get(f), (int, float))}
            if sauber:
                h.setdefault(art, {})[str(k)[:10]] = sauber
                zahl += 1
    h["tag"] = dict(sorted(h.get("tag", {}).items())[-1500:])
    h["stand"] = datetime.datetime.now().isoformat(timespec="minutes")
    with open(HISTORIE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False)
    return {"ok": True, "eingelesen": zahl, "monate": len(h.get("monat", {})), "tage": len(h.get("tag", {}))}


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else "lesen"
    if aktion == "holen":
        print(json.dumps(holen(), ensure_ascii=False))
    elif aktion == "import":
        print(json.dumps(importieren(sys.argv[2:]), ensure_ascii=False))
    else:
        d = laden()
        try:
            d["aus_akte"] = akte_durchsuchen()
        except Exception:  # noqa: BLE001 – Lesen soll nie daran scheitern
            d["aus_akte"] = 0
        d["historie"] = historie_laden()
        d["historie"].pop("dateien", None)
        d["ok"] = True
        print(json.dumps(d, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": f"{type(fehler).__name__}: {str(fehler)[:200]}"}, ensure_ascii=False))
