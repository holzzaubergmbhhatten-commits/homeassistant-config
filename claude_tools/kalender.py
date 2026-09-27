#!/usr/bin/env python3
"""Termine im lokalen Kalender "Termine" (Geburtstage) ändern oder löschen.

Home Assistant kann Termine nur anlegen, nicht ändern/löschen. Dieses Skript bearbeitet
deshalb direkt die Kalenderdatei (/config/.storage/local_calendar.*.ics). Danach lädt
Home Assistant den Kalender neu (siehe packages/telegram.yaml).

Aufruf: python3 kalender.py <base64-JSON>
JSON: {"aktion": "aendern"|"loeschen", "alt_titel": str, "alt_datum": "JJJJ-MM-TT",
       "titel": str, "datum": "JJJJ-MM-TT", "uhrzeit": "HH:MM", "dauer_minuten": int|str}
Ausgabe (stdout): eine Zeile Text für die Antwort im Telegram-Chat.
"""
import base64
import datetime as dt
import glob
import json
import os
import re
import shutil
import sys
import zoneinfo

TZ = zoneinfo.ZoneInfo("Europe/Berlin")
TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
SICHERUNG = "/media/kalender_sicherung"  # außerhalb von Git, bleibt bei jedem Update erhalten


def speichere(datei, inhalt):
    """Vor jeder Änderung eine Sicherheitskopie ablegen (die letzten 50 bleiben)."""
    os.makedirs(SICHERUNG, exist_ok=True)
    stempel = dt.datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S")
    shutil.copy2(datei, os.path.join(SICHERUNG, f"{stempel}_{os.path.basename(datei)}"))
    for alt in sorted(glob.glob(os.path.join(SICHERUNG, "*.ics")))[:-50]:
        os.remove(alt)
    with open(datei, "w", encoding="utf-8", newline="") as f:
        f.write(inhalt)


def lese_zeitpunkt(zeile):
    """DTSTART/DTEND-Zeile → (datetime lokal oder date, ganztägig?)."""
    m = re.match(r"^DT(?:START|END)(;[^:]*)?:(\S+)$", zeile)
    params, wert = (m.group(1) or ""), m.group(2)
    if "VALUE=DATE" in params or re.fullmatch(r"\d{8}", wert):
        return dt.datetime.strptime(wert[:8], "%Y%m%d").date(), True
    zeit = dt.datetime.strptime(wert[:15], "%Y%m%dT%H%M%S")
    if wert.endswith("Z"):
        zeit = zeit.replace(tzinfo=dt.timezone.utc).astimezone(TZ)
    else:
        tz = re.search(r"TZID=([^;:]+)", params)
        zeit = zeit.replace(tzinfo=zoneinfo.ZoneInfo(tz.group(1)) if tz else TZ).astimezone(TZ)
    return zeit, False


def schreibe_zeitpunkt(name, wert, ganztags):
    if ganztags:
        return f"{name};VALUE=DATE:{wert.strftime('%Y%m%d')}"
    return f"{name}:{wert.astimezone(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def text(wert):
    return (wert or "").strip()


def beschreibe(titel, start, ganztags):
    tag = start if ganztags else start.date()
    s = f"{titel} am {TAGE[tag.weekday()]} {tag.strftime('%d.%m.%Y')}"
    return s + (" (ganztägig)" if ganztags else f" um {start.strftime('%H:%M')} Uhr")


def main():
    auftrag = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
    aktion = auftrag.get("aktion")
    alt_titel = text(auftrag.get("alt_titel")).lower()
    alt_datum = text(auftrag.get("alt_datum"))

    dateien = sorted(glob.glob("/config/.storage/local_calendar.geburtstage*.ics")) or sorted(
        glob.glob("/config/.storage/local_calendar.*.ics"))
    for datei in dateien:
        with open(datei, encoding="utf-8", newline="") as f:
            roh = f.read()
        nl = "\r\n" if "\r\n" in roh else "\n"
        inhalt = re.sub(r"\r?\n[ \t]", "", roh)  # Zeilenumbrüche (Folding) auflösen
        bloecke = list(re.finditer(r"BEGIN:VEVENT.*?END:VEVENT", inhalt, re.S))
        treffer = []
        for b in bloecke:
            zeilen = b.group(0).splitlines()
            summary = next((z[8:] for z in zeilen if z.startswith("SUMMARY")), "")
            summary = summary.split(":", 1)[-1] if summary.startswith(";") else summary.lstrip(":")
            start_z = next((z for z in zeilen if z.startswith("DTSTART")), None)
            if not start_z:
                continue
            start, ganz = lese_zeitpunkt(start_z)
            tag = start if ganz else start.date()
            if alt_datum and tag.isoformat() != alt_datum:
                continue
            if alt_titel and alt_titel not in summary.lower() and summary.lower() not in alt_titel:
                continue
            treffer.append((b, zeilen, summary, start, ganz))
        if not treffer:
            continue
        if len(treffer) > 1 and not alt_titel:
            print(f"❓ Am {alt_datum} gibt es mehrere Termine – bitte den Titel dazuschreiben.")
            return
        b, zeilen, summary, start, ganz = treffer[0]
        if any(z.startswith("RRULE") for z in zeilen):
            print(f"🔁 {summary} ist ein Serientermin – den bitte am Handy im Kalender ändern.")
            return
        ende_z = next((z for z in zeilen if z.startswith("DTEND")), None)
        ende, _ = lese_zeitpunkt(ende_z) if ende_z else (None, ganz)

        if aktion == "loeschen":
            neu_inhalt = inhalt[: b.start()] + inhalt[b.end():].lstrip("\r\n")
            neu_inhalt = re.sub(r"(END:VEVENT)(BEGIN:VEVENT)", r"\1" + nl + r"\2", neu_inhalt)
            speichere(datei, neu_inhalt)
            print("🗑️ Gelöscht: " + beschreibe(summary, start, ganz))
            return

        # Ändern: nicht genannte Angaben bleiben wie sie sind
        titel = text(auftrag.get("titel")) or summary
        datum = text(auftrag.get("datum"))
        uhrzeit = text(auftrag.get("uhrzeit"))
        neu_tag = dt.date.fromisoformat(datum) if datum else (start if ganz else start.date())
        if ganz and not uhrzeit:
            dauer_tage = max(1, ((ende - start).days if ende else 1))
            n_start, n_ende, n_ganz = neu_tag, neu_tag + dt.timedelta(days=dauer_tage), True
        else:
            if uhrzeit:
                h, m = [int(x) for x in re.findall(r"\d+", uhrzeit)[:2]]
            else:
                h, m = start.hour, start.minute
            try:
                minuten = int(float(text(str(auftrag.get("dauer_minuten") or ""))))
            except ValueError:
                minuten = 0
            if minuten <= 0:
                minuten = int((ende - start).total_seconds() // 60) if (ende and not ganz) else 60
            n_start = dt.datetime(neu_tag.year, neu_tag.month, neu_tag.day, h, m, tzinfo=TZ)
            n_ende, n_ganz = n_start + dt.timedelta(minutes=minuten), False

        neue_zeilen = []
        for z in zeilen:
            if z.startswith("SUMMARY"):
                z = "SUMMARY:" + titel
            elif z.startswith("DTSTART"):
                z = schreibe_zeitpunkt("DTSTART", n_start, n_ganz)
            elif z.startswith("DTEND"):
                z = schreibe_zeitpunkt("DTEND", n_ende, n_ganz)
            elif z.startswith("SEQUENCE:"):
                z = "SEQUENCE:" + str(int(z.split(":", 1)[1] or 0) + 1)
            neue_zeilen.append(z)
        if not ende_z:
            neue_zeilen.insert(-1, schreibe_zeitpunkt("DTEND", n_ende, n_ganz))
        neu_inhalt = inhalt[: b.start()] + nl.join(neue_zeilen) + inhalt[b.end():]
        speichere(datei, neu_inhalt)
        print("✏️ Geändert: " + beschreibe(titel, n_start, n_ganz))
        return

    print(f"❓ Diesen Termin habe ich nicht gefunden ({auftrag.get('alt_titel') or '?'}, {alt_datum or '?'}).")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # Antwort soll im Chat ankommen statt im Log zu verschwinden
        print(f"⚠️ Termin konnte nicht bearbeitet werden: {fehler}")
