#!/usr/bin/env python3
"""Gedächtnis des Telegram-Bots: merkt sich je Chat die letzten Nachrichten (Familie und Bot), damit der Bot auf
„danach“, „das war falsch“, „genau wie beim Dodge“ usw. richtig reagiert – auch nach Stunden.

Liegt nur lokal in /config/telegram_verlauf.json (nicht im Repository). Je Chat höchstens 200 Einträge, älter als
14 Tage fällt raus.

Aufruf:  chatverlauf.py add <base64-JSON {chat, wer, text}>
         chatverlauf.py get <base64-JSON {chat, ohne}>   → Text der letzten Nachrichten (älteste zuerst)"""
import base64
import datetime
import fcntl
import json
import sys

DATEI = "/config/telegram_verlauf.json"
SPERRE = "/config/.telegram_verlauf.lock"
MAX, TAGE, ZEIGEN, ZEICHEN = 200, 14, 40, 600


def laden():
    try:
        with open(DATEI, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def hinzufuegen(chat, wer, text):
    text = str(text or "").strip()
    if not chat or not text:
        return
    with open(SPERRE, "w") as sp:
        fcntl.flock(sp, fcntl.LOCK_EX)
        d = laden()
        grenze = (datetime.datetime.now() - datetime.timedelta(days=TAGE)).isoformat(timespec="seconds")
        liste = [e for e in d.get(str(chat), []) if e.get("zeit", "") >= grenze]
        liste.append({"zeit": datetime.datetime.now().isoformat(timespec="seconds"), "wer": str(wer or "")[:30],
                      "text": text[:2000]})
        d[str(chat)] = liste[-MAX:]
        with open(DATEI, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)


def lesen(chat, ohne=""):
    liste = laden().get(str(chat), [])
    ohne = str(ohne or "").strip()
    # die gerade eingegangene Nachricht steht evtl. schon drin – nicht doppelt zeigen
    if ohne and liste and liste[-1].get("text", "").strip() == ohne:
        liste = liste[:-1]
    zeilen = []
    for e in liste[-ZEIGEN:]:
        try:
            z = datetime.datetime.fromisoformat(e["zeit"]).strftime("%d.%m. %H:%M")
        except (KeyError, ValueError):
            z = ""
        t = " ".join(str(e.get("text", "")).split())
        zeilen.append(f"[{z}] {e.get('wer') or '?'}: {t[:ZEICHEN]}{'…' if len(t) > ZEICHEN else ''}")
    return "\n".join(zeilen)


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else ""
    daten = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8")) if len(sys.argv) > 2 else {}
    if aktion == "add":
        hinzufuegen(daten.get("chat"), daten.get("wer"), daten.get("text"))
        print("ok")
    elif aktion == "get":
        print(lesen(daten.get("chat"), daten.get("ohne")))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001 – das Gedächtnis darf den Bot nie aufhalten
        print("")
        sys.stderr.write(f"{type(fehler).__name__}: {fehler}\n")
