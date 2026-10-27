#!/usr/bin/env python3
"""Fragen zum Haus beantworten („Wie bekomme ich die Sicherung der Waschmaschine aus?“, „Wo ist der Haupthahn?“) –
mit allem, was die Familie schon gesammelt hat: Haus-Handbuch (Webseite, Link nur in input_text.zuhause_seite_link),
Fotos im Eingang (Typenschilder, Sicherungskästen …) und passende Dokumente aus der Akte.

Aufruf: handbuch.py frage <base64-JSON {frage, link, von}>  → {"ok": true, "antwort": "…"}
Das Handbuch wird zwischengespeichert (/config/handbuch_cache.json, höchstens 6 Stunden alt)."""
import base64
import html
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CACHE = "/config/handbuch_cache.json"
SEITEN = ["index", "sicherungen", "haustechnik", "geraete", "maschinen", "netzwerk", "nummern", "wo-ist-was", "wohnwagen",
          "wartung", "grundriss", "offene-fragen", "packliste"]
DATEN = ["wo-daten.js", "maschinen-daten.js"]

FRAGE = """Du hilfst einer Familie auf ihrem Resthof (Haus, Nebengebäude, Werkstatt, Stellplätze) bei praktischen Fragen zum Haus.
Unten steht alles, was sie gesammelt hat: ihr Haus-Handbuch (Sicherungsplan, Haustechnik, Geräte, Maschinen, Wo ist was …),
Fotos mit erkannten Infos und passende Dokumente. Antworte auf Deutsch, kurz, konkret und in Schritten:
WO genau (Verteiler, Raum, Sicherungsnummer wie F23, FI-Gruppe), WAS zu tun ist, worauf man achten muss (Sicherheit).
Nenne die Quelle in Klammern (z. B. „laut Sicherungsplan“). Steht es nicht drin, sag das ehrlich und gib nur dann einen
allgemeinen, sicheren Rat; schlage vor, was man ins Handbuch eintragen sollte. Erfinde keine Sicherungsnummern.
Bei Strom: vor Arbeiten an Leitungen/Geräten immer die Sicherung aus, bei Unsicherheit Elektriker.
Antworte NUR mit JSON: {"antwort": "Text für Telegram/Sprache (max. ca. 12 Zeilen)"}"""


def text_aus_html(s):
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</(p|div|li|tr|h\d)>", "\n", s, flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def holen(url):
    req = urllib.request.Request(url, headers={"User-Agent": "HomeAssistant-Handbuch"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "replace")


def handbuch(link):
    """Text aller Handbuch-Seiten (inkl. auf dem Server eingespielter/ergänzter Inhalte), zwischengespeichert."""
    try:
        with open(CACHE, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("link") == link and time.time() - c.get("zeit", 0) < 6 * 3600:
            return c["text"]
    except (OSError, ValueError, KeyError):
        pass
    if not re.match(r"^https://", link or ""):
        return ""
    letzter = link.rstrip("/").rsplit("/", 1)[-1]
    basis = (link.rsplit("/", 1)[0] + "/") if "." in letzter and not link.endswith("/") else link.rstrip("/") + "/"
    teile = []
    for s in SEITEN:
        try:
            teile.append(f"=== Seite {s} ===\n" + text_aus_html(holen(basis + s + ".html")))
        except Exception:  # noqa: BLE001
            pass
    for d in DATEN:
        try:
            teile.append(f"=== Daten {d} ===\n" + holen(basis + d)[:40000])
        except Exception:  # noqa: BLE001
            pass
    try:   # Ergänzungen, Notizen und eingespielte Seiten vom Server
        items = json.loads(holen(basis + "api.php?a=get&x=1")).get("items") or {}
        for k, v in items.items():
            wert = v.get("v") if isinstance(v, dict) else v
            if isinstance(wert, str) and wert.strip():
                teile.append(f"=== Ergänzung {k} ===\n" + (text_aus_html(wert) if "<" in wert else wert)[:20000])
    except Exception:  # noqa: BLE001
        pass
    text = "\n\n".join(teile)[:250000]
    if text:
        try:
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump({"link": link, "zeit": time.time(), "text": text}, f, ensure_ascii=False)
        except OSError:
            pass
    return text


def eingang_text():
    try:
        with open("/config/eingang.json", encoding="utf-8") as f:
            liste = json.load(f)
    except (OSError, ValueError):
        return ""
    return "\n".join(f"- {e.get('titel')} ({e.get('zuordnung') or e.get('bereich')}): {e.get('text') or ''} {e.get('erkannt') or ''}"[:800]
                     for e in liste[-150:])


def akte_text(frage):
    try:
        import akte
        liste = akte.verzeichnis()
        treffer = akte.suchen(liste, frage, 6, mindest=2)
        return "\n".join(f"- {liste[i].get('titel')} ({liste[i].get('absender')}, {liste[i].get('datum')}): "
                         f"{(liste[i].get('inhalt') or '')[:1500]}" for i in treffer)
    except Exception:  # noqa: BLE001
        return ""


def frage(auftrag):
    import anthropic
    import garten_ki
    f = (auftrag.get("frage") or "").strip()
    if not f:
        return {"ok": False, "fehler": "keine Frage"}
    hb = handbuch(auftrag.get("link") or "")
    inhalt = (f"FOTOS IM EINGANG:\n{eingang_text() or '(keine)'}\n\nDOKUMENTE AUS DER AKTE:\n{akte_text(f) or '(keine passenden)'}\n\n"
              f"Frage{' von ' + auftrag['von'] if auftrag.get('von') else ''}: {f}")
    client = anthropic.Anthropic(api_key=garten_ki.api_schluessel(), timeout=50, max_retries=1)
    a = client.messages.create(model=garten_ki.MODELL, max_tokens=1200,
                               # Handbuch als zwischengespeicherter Block: weitere Fragen gehen schneller und günstiger
                               system=[{"type": "text", "text": FRAGE},
                                       {"type": "text", "text": "HAUS-HANDBUCH:\n" + (hb or "(nicht erreichbar – Link in "
                                        "input_text.zuhause_seite_link fehlt?)"), "cache_control": {"type": "ephemeral"}}],
                               messages=[{"role": "user", "content": [{"type": "text", "text": inhalt}]}],
                               extra_body={"output_config": {"effort": "low"}, "fallbacks": "default"},
                               extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"})
    roh = "".join(b.text for b in a.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", roh, re.S)
    try:
        antwort = json.loads(m.group(0)).get("antwort") if m else roh
    except ValueError:
        antwort = roh
    return {"ok": True, "antwort": (antwort or "Dazu habe ich nichts gefunden.").strip()[:3500], "handbuch": bool(hb)}


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else ""
    auftrag = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8")) if len(sys.argv) > 2 else {}
    if aktion == "frage":
        print(json.dumps(frage(auftrag), ensure_ascii=False))
    else:
        print(json.dumps({"ok": False, "fehler": "unbekannte Aktion"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": f"{type(fehler).__name__}: {str(fehler)[:200]}"}, ensure_ascii=False))
