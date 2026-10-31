#!/usr/bin/env python3
"""Küche: Essensplan für die Woche, Rezepte, Vorrat & Ernte, Einkaufsliste – mit Claude (packages/kueche.yaml, www/kueche.html).

Aufrufe:
  kueche.py speichern <base64-Stücke>        Daten von der Küchen-Seite speichern (JSON, siehe unten)
  kueche.py stand                            kurzer Stand für sensor.kueche_heute (heute, die Woche)
  kueche.py einkauf <base64-JSON {von, bis}> Zutaten der Tage zusammenrechnen → [{text, notiz, bereich}] (ohne Basis/Vorrat)
  kueche.py telegram <base64-JSON {text, chat, von, termine, wetter}>
            Nachricht an den Bot ("Was gibt's heute?", "Lasagne am Samstag", "Ernte: 3 Kürbisse", Rezept-Link …):
            Claude antwortet sofort; längere Arbeit (Woche planen, Rezept holen) läuft danach im Hintergrund weiter.
  kueche.py ki <base64-JSON {art: plan|tausch|rezept, …, termine, wetter, chat}>
            Läuft im Hintergrund (Home Assistant wartet höchstens 60 Sekunden). Fortschritt in kueche_status.json,
            Ergebnis direkt in kueche_daten.json; mit "chat" kommt die Antwort zusätzlich per Telegram.

Daten (lokal, nicht im Repository): /config/www/kueche_daten.json
  {einstellungen: {erwachsene, kinder: [{alter}], tage: [0..6], budget, stil: [], reste, ernaehrung, allergien: [], zeit,
                   geraete: [], platz: [], arbeitszeiten, hinweise, laden},
   rezepte: [{id, titel, kurz, portionen, zeit_min, zutaten: [{menge, einheit, name, bereich, basis}],
              schritte: [{text, timer_min}], quelle, favorit, notiz}],
   plan: {"JJJJ-MM-TT": {art: kochen|reste|auswaerts|frei, titel, kurz, grund, portionen, zeit_min, kosten_eur,
                         zutaten, schritte, rezept_id, gekocht}},
   vorrat: [{name, menge, quelle: ernte|vorrat, seit}], hinweis_woche: {"JJJJ-MM-TT": "…"}}
Schlüssel kommen aus den Integrationen (Anthropic, Telegram), nicht aus dem Repository.
"""
import base64
import fcntl
import html as html_mod
import io
import json
import os
import re
import sys
import time
import uuid
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATEN = "/config/www/kueche_daten.json"
STATUS = "/config/www/kueche_status.json"
SPERRE = "/config/.kueche.lock"
MUCKI = "/config/www/mucki_daten.json"

TAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
BEREICHE = ["Obst & Gemüse", "Brot & Backwaren", "Kühlregal & Milch", "Fleisch & Fisch", "Tiefkühl",
            "Nudeln, Reis & Konserven", "Gewürze, Öl & Backen", "Getränke", "Sonstiges"]

STANDARD = {
    "einstellungen": {"erwachsene": 2, "kinder": [{"alter": 8}], "kinder_gleich": True, "tage": [0, 1, 2, 3, 4, 5, 6],
                      "budget": 75, "stil": ["Familienlieblinge"], "reste": "1", "ernaehrung": "keine", "allergien": [],
                      "zeit": 30, "geraete": ["Herd", "Backofen"], "platz": ["Kühlschrank", "Gefrierschrank"],
                      "arbeitszeiten": "", "hinweise": "", "laden": "Rewe", "eingerichtet": False},
    "rezepte": [], "plan": {}, "vorrat": [], "hinweis_woche": {},
}


# ---------- Dateien ----------

def json_laden(pfad, leer):
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, type(leer)) else leer
    except (OSError, ValueError):
        return leer


def json_schreiben(pfad, d):
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, pfad)


def daten_laden():
    d = json_laden(DATEN, {})
    for k, v in STANDARD.items():
        if k not in d or not isinstance(d[k], type(v)):
            d[k] = json.loads(json.dumps(v))
    for k, v in STANDARD["einstellungen"].items():
        d["einstellungen"].setdefault(k, v)
    return d


class Sperre:
    def __enter__(self):
        self.f = open(SPERRE, "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def status(laeuft, text="", fehler="", art=""):
    try:
        json_schreiben(STATUS, {"laeuft": laeuft, "text": text, "fehler": fehler, "art": art,
                                "zeit": datetime.now().isoformat(timespec="seconds")})
    except OSError:
        pass


# ---------- Hilfen ----------

def montag(d):
    return d - timedelta(days=d.weekday())


def de(d):
    return f"{TAGE[d.weekday()]}, {d.strftime('%d.%m.')}"


def portionen(e):
    """Portionen aus den Einstellungen: Erwachsene 1, Kinder bis 6 halbe, bis 12 dreiviertel (gerundet)."""
    p = float(e.get("erwachsene") or 0)
    for k in e.get("kinder") or []:
        a = int((k or {}).get("alter") or 8)
        p += 0.5 if a <= 6 else 0.75 if a <= 12 else 1
    return max(1, round(p))


def zutaten_sauber(liste):
    aus = []
    for z in liste or []:
        if not isinstance(z, dict) or not str(z.get("name", "")).strip():
            continue
        try:
            menge = float(str(z.get("menge", "")).replace(",", ".")) if str(z.get("menge", "")).strip() else None
        except ValueError:
            menge = None
        bereich = z.get("bereich") if z.get("bereich") in BEREICHE else "Sonstiges"
        aus.append({"menge": menge, "einheit": str(z.get("einheit") or "")[:12], "name": str(z["name"]).strip()[:60],
                    "bereich": bereich, "basis": bool(z.get("basis"))})
    return aus


def schritte_sauber(liste):
    aus = []
    for s in liste or []:
        if isinstance(s, str):
            s = {"text": s}
        if not isinstance(s, dict) or not str(s.get("text", "")).strip():
            continue
        try:
            t = int(float(s.get("timer_min") or 0))
        except (TypeError, ValueError):
            t = 0
        aus.append({"text": str(s["text"]).strip()[:600], "timer_min": max(0, min(t, 600))})
    return aus


def gericht_sauber(g):
    art = g.get("art") if g.get("art") in ("kochen", "reste", "auswaerts", "frei") else "kochen"
    aus = {"art": art, "titel": str(g.get("titel") or "")[:80], "kurz": str(g.get("kurz") or "")[:200],
           "grund": str(g.get("grund") or "")[:200], "zeit_min": int(float(g.get("zeit_min") or 0) or 0),
           "portionen": int(float(g.get("portionen") or 0) or 0), "nutzt_vorrat": [str(x)[:40] for x in g.get("nutzt_vorrat") or []][:6]}
    try:
        aus["kosten_eur"] = round(float(g.get("kosten_eur") or 0), 2)
    except (TypeError, ValueError):
        aus["kosten_eur"] = 0
    if art == "kochen":
        aus["zutaten"] = zutaten_sauber(g.get("zutaten"))
        aus["schritte"] = schritte_sauber(g.get("schritte"))
    if g.get("rezept_id"):
        aus["rezept_id"] = str(g["rezept_id"])[:40]
    return aus


def stundenplan_text():
    """Mathildas Stundenplan (Muckis Seite) kurz: je Wochentag, bis wann Schule/Betreuung geht."""
    d = json_laden(MUCKI, {})
    zeilen = d.get("zeilen") or []
    if not zeilen:
        return ""
    aus = []
    for i, tag in enumerate(TAGE[:5]):
        letzte = ""
        for z in zeilen:
            f = (z.get("faecher") or [])
            if not z.get("info") and i < len(f) and str((f[i] or {}).get("fach", "")).strip():
                letzte = f"{f[i]['fach']} ({z.get('zeit', '').splitlines()[-1] if z.get('zeit') else ''})"
        if letzte:
            aus.append(f"{tag}: letzte Stunde {letzte}")
    return "; ".join(aus)


def garten_text():
    try:
        import garten_ki
        return garten_ki.plan_aus_datei()[:800]
    except Exception:  # noqa: BLE001
        return ""


def einstellungen_text(e):
    k = e.get("kinder") or []
    teile = [f"Für {e.get('erwachsene', 2)} Erwachsene" + (" und Kinder im Alter von " + ", ".join(str(x.get('alter')) for x in k) if k else "")
             + f" → {portionen(e)} Portionen pro Mahlzeit.",
             f"Wir kochen normalerweise an: {', '.join(TAGE[t] for t in sorted(e.get('tage') or []))}.",
             f"Wochenbudget fürs Abendessen: ca. {e.get('budget', 75)} € (Laden: {e.get('laden') or 'Supermarkt'}).",
             f"Stil: {', '.join(e.get('stil') or []) or 'von allem etwas'}.",
             {"0": "Reste: jeden Abend frisch kochen.", "1": "Reste: 1 freier Abend pro Woche (ein Gericht doppelt kochen, am nächsten Tag Reste).",
              "2": "Reste: 2 freie Abende (zweimal groß kochen).", "3": "Reste: 3 freie Abende (wenig kochen, viel Ruhe)."}.get(str(e.get("reste")), ""),
             f"Ernährung: {e.get('ernaehrung') or 'keine Einschränkung'}." + (" Kinder essen dasselbe." if e.get("kinder_gleich", True) else ""),
             ("ALLERGIEN – diese Zutaten NIE verwenden: " + ", ".join(e["allergien"]) + ".") if e.get("allergien") else "Keine Allergien.",
             f"Zeit zum Kochen an einem normalen Wochenabend: {e.get('zeit', 30)} Minuten (am Wochenende darf es mehr sein).",
             f"Küchengeräte: {', '.join(e.get('geraete') or []) or 'Herd, Backofen'}. Platz für Reste: {', '.join(e.get('platz') or []) or 'Kühlschrank'}."]
    if e.get("arbeitszeiten"):
        teile.append(f"Arbeitszeiten / wann wir abends da sind: {e['arbeitszeiten']}")
    if e.get("hinweise"):
        teile.append(f"Unsere Hinweise: {e['hinweise']}")
    return "\n".join(t for t in teile if t)


def vorrat_text(d):
    v = [f"{x.get('name')}{' (' + str(x.get('menge')) + ')' if x.get('menge') else ''}{' – eigene Ernte' if x.get('quelle') == 'ernte' else ''}"
         for x in d.get("vorrat") or [] if isinstance(x, dict) and x.get("name")]
    return ", ".join(v)


def termine_text(termine, von, bis):
    aus = []
    for t in termine or []:
        s = str(t.get("start", ""))
        if von.isoformat() <= s[:10] <= bis.isoformat():
            try:
                dt = date.fromisoformat(s[:10])
            except ValueError:
                continue
            aus.append(f"{de(dt)}{' ' + s[11:16] if 'T' in s else ' ganztägig'}"
                       f"{'–' + str(t.get('end', ''))[11:16] if 'T' in str(t.get('end', '')) else ''}: {t.get('summary', '')}")
    return "\n".join(aus)


# ---------- Claude ----------

def claude(system, inhalt, max_tokens=4000, effort="low", timeout=240):
    import anthropic
    import garten_ki
    client = anthropic.Anthropic(api_key=garten_ki.api_schluessel(), timeout=timeout, max_retries=1)
    a = client.messages.create(model=garten_ki.MODELL, max_tokens=max_tokens, system=system,
                               messages=[{"role": "user", "content": inhalt}],
                               extra_body={"output_config": {"effort": effort}, "fallbacks": "default"},
                               extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"})
    if a.stop_reason == "refusal":
        raise RuntimeError("Claude hat die Anfrage abgelehnt")
    roh = "".join(b.text for b in a.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", roh, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        raise RuntimeError("Antwort von Claude war unvollständig – bitte nochmal versuchen")


GRUND = """Du bist der Familienkoch und Essensplaner einer Familie in Norddeutschland (Wesermarsch, Resthof mit eigenem Gemüsegarten).
Du planst alltagstaugliche, abwechslungsreiche Abendessen, die die Familie wirklich kocht: deutsche Hausmannskost und
beliebte internationale Gerichte, saisonal (Monat beachten!), mit Zutaten aus jedem deutschen Supermarkt.
Eigene Ernte und Vorrat zuerst verbrauchen. Termine beachten: An Tagen mit Terminen am Abend (Training, Elternabend, spät
nach Hause) etwas Schnelles, Vorbereitetes oder Reste planen; an ruhigen Wochenenden darf es aufwendiger sein.
Kinderfreundlich, wenn Kinder mitessen. Allergien und Ernährungsform IMMER einhalten.
Mengen immer für die angegebene Portionenzahl. Einheiten: g, kg, ml, l, Stück, EL, TL, Prise, Bund, Dose, Packung, Zehe.
Bereiche für die Einkaufsliste genau so: """ + ", ".join(BEREICHE) + """.
"basis": true nur für Dinge, die man meist im Haus hat (Salz, Pfeffer, Öl, Zucker, Mehl, Brühe, Gewürze, Essig, Senf).
Schritte kurz und klar (ein Handgriff pro Schritt, so dass man sie am Monitor in der Küche nacheinander abtippen kann);
"timer_min" > 0, wenn in dem Schritt etwas eine feste Zeit braucht (kochen, backen, ziehen lassen), sonst 0.
Kosten grob schätzen (deutsche Supermarktpreise, ohne Basiszutaten). Alles auf Deutsch. Keine Emojis."""

GERICHT_FORMAT = """{"art": "kochen" | "reste" | "auswaerts" | "frei", "titel": "…", "kurz": "ein Satz, was es ist",
 "grund": "kurz, warum an diesem Tag (z. B. 'Training bis 19 Uhr – geht schnell')", "zeit_min": 25, "portionen": 3,
 "kosten_eur": 9.5, "nutzt_vorrat": ["Kürbis"],
 "zutaten": [{"menge": 500, "einheit": "g", "name": "Hackfleisch", "bereich": "Fleisch & Fisch", "basis": false}],
 "schritte": [{"text": "…", "timer_min": 0}], "rezept_id": "nur wenn es ein gespeichertes Rezept ist"}"""


def kontext(d, auftrag, von, bis):
    e = d["einstellungen"]
    teile = [f"Heute ist {de(date.today())} {date.today().year}.", "Unsere Wünsche:\n" + einstellungen_text(e)]
    t = termine_text(auftrag.get("termine"), von, bis)
    teile.append("Unsere Termine in dem Zeitraum:\n" + (t or "keine eingetragen"))
    s = stundenplan_text()
    if s:
        teile.append("Stundenplan unserer Tochter Mathilda (Grundschule, Mo–Fr): " + s)
    v = vorrat_text(d)
    if v:
        teile.append("Vorrat und eigene Ernte, bitte mit einplanen: " + v)
    g = garten_text()
    if g:
        teile.append("Was gerade im Garten wächst (Pflanzplan): " + g)
    if auftrag.get("wetter"):
        teile.append(f"Wetter: {auftrag['wetter']}")
    fav = [f"{r['id']}: {r.get('titel')}" for r in d.get("rezepte") or [] if r.get("favorit")][:30]
    andere = [f"{r['id']}: {r.get('titel')}" for r in d.get("rezepte") or [] if not r.get("favorit")][-30:]
    if fav:
        teile.append("Unsere Lieblingsrezepte (gern 1–2 pro Woche einbauen, dann rezept_id angeben): " + "; ".join(fav))
    if andere:
        teile.append("Weitere gespeicherte Rezepte: " + "; ".join(andere))
    vorher = sorted((k, v.get("titel", "")) for k, v in (d.get("plan") or {}).items()
                    if (von - timedelta(days=21)).isoformat() <= k < von.isoformat() and v.get("titel"))
    if vorher:
        teile.append("Das gab es zuletzt (nicht wiederholen): " + ", ".join(x[1] for x in vorher))
    return "\n\n".join(teile)


def rezept_einsetzen(d, g):
    """Gespeichertes Rezept übernehmen, wenn Claude eins ausgesucht hat und keine eigenen Zutaten mitliefert."""
    rid = g.get("rezept_id")
    r = next((x for x in d.get("rezepte") or [] if x.get("id") == rid), None) if rid else None
    if r and not g.get("zutaten"):
        g["zutaten"], g["schritte"] = r.get("zutaten", []), r.get("schritte", [])
        g.setdefault("zeit_min", r.get("zeit_min", 0))
    return g


# ---------- Aufgaben im Hintergrund ----------

def plan_machen(auftrag):
    d = daten_laden()
    start = date.fromisoformat(auftrag.get("von") or montag(date.today() + timedelta(days=2)).isoformat())
    tage = int(auftrag.get("tage") or 7)
    bis = start + timedelta(days=tage - 1)
    if auftrag.get("nur_wenn_leer") and any(start.isoformat() <= k <= bis.isoformat() for k in d.get("plan") or {}):
        raise LeiseFertig()
    if auftrag.get("nur_wenn_leer") and not d["einstellungen"].get("eingerichtet"):
        raise LeiseFertig()
    feste = {k: v for k, v in (d.get("plan") or {}).items() if start.isoformat() <= k <= bis.isoformat() and v.get("fest")}
    liste = [start + timedelta(days=i) for i in range(tage)]
    frage = (kontext(d, auftrag, start, bis)
             + f"\n\nPlane die Abendessen für {de(start)} bis {de(bis)} – also für diese Tage: "
             + ", ".join(f"{de(x)} ({x.isoformat()})" for x in liste)
             + ("\nDiese Tage stehen schon fest, nicht ändern, aber berücksichtigen: "
                + "; ".join(f"{k}: {v.get('titel')}" for k, v in sorted(feste.items())) if feste else "")
             + (f"\nBesonderer Wunsch: {auftrag['wunsch']}" if auftrag.get("wunsch") else "")
             + "\nTage, an denen wir laut Einstellungen nicht kochen: art \"frei\" (titel z. B. \"Brotzeit\" oder \"Auswärts\")."
             + "\nReste-Abende: art \"reste\", titel \"Reste: <Gericht>\" – das Gericht am Vortag dann mit doppelter Portionenzahl planen."
             + "\nAntworte NUR mit JSON: {\"tage\": [{\"datum\": \"JJJJ-MM-TT\", …Gericht…}], \"hinweis\": \"1–2 Sätze zur Woche\","
             + " \"kosten_gesamt_eur\": 70}\nGericht-Format: " + GERICHT_FORMAT)
    status(True, "Claude plant die Woche …", art="plan")
    a = claude(GRUND, frage, max_tokens=16000, effort="medium", timeout=300)
    with Sperre():
        d = daten_laden()
        for g in a.get("tage") or []:
            k = str(g.get("datum", ""))
            if k in feste or not re.match(r"^\d{4}-\d\d-\d\d$", k) or not (start.isoformat() <= k <= bis.isoformat()):
                continue
            d["plan"][k] = gericht_sauber(rezept_einsetzen(d, g))
        if a.get("hinweis"):
            d["hinweis_woche"][montag(start).isoformat()] = str(a["hinweis"])[:300] + (
                f" Geschätzte Kosten: ca. {round(float(a['kosten_gesamt_eur']))} €." if a.get("kosten_gesamt_eur") else "")
        # alte Pläne (älter als 8 Wochen) entfernen
        grenze = (date.today() - timedelta(days=56)).isoformat()
        d["plan"] = {k: v for k, v in d["plan"].items() if k >= grenze}
        json_schreiben(DATEN, d)
    text = "Essensplan " + de(start) + " – " + de(bis) + ":\n" + "\n".join(
        f"• {TAGE[date.fromisoformat(k).weekday()][:2]}: {v.get('titel')}" for k, v in sorted(d["plan"].items())
        if start.isoformat() <= k <= bis.isoformat())
    return text + ("\n" + d["hinweis_woche"].get(montag(start).isoformat(), "") if d["hinweis_woche"].get(montag(start).isoformat()) else "")


class LeiseFertig(Exception):
    """Nichts zu tun (z. B. automatische Planung, aber die Woche ist schon geplant) – ohne Nachricht."""


def tausch_machen(auftrag):
    d = daten_laden()
    tag = date.fromisoformat(auftrag["datum"])
    alt = (d.get("plan") or {}).get(tag.isoformat(), {})
    frage = (kontext(d, auftrag, tag, tag)
             + f"\n\nPlane ein Abendessen für {de(tag)}."
             + (f" Bisher geplant war: {alt.get('titel')} – bitte etwas anderes." if alt.get("titel") and not auftrag.get("wunsch") else "")
             + (f" Unser Wunsch: {auftrag['wunsch']}" if auftrag.get("wunsch") else "")
             + "\nAntworte NUR mit JSON im Gericht-Format: " + GERICHT_FORMAT)
    status(True, f"Claude sucht ein neues Gericht für {de(tag)} …", art="tausch")
    g = claude(GRUND, frage, max_tokens=5000, effort="low")
    with Sperre():
        d = daten_laden()
        d["plan"][tag.isoformat()] = gericht_sauber(rezept_einsetzen(d, g))
        json_schreiben(DATEN, d)
    return f"{de(tag)}: {g.get('titel')} – {g.get('kurz', '')}"


def seite_holen(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (HomeAssistant Küche)", "Accept-Language": "de"})
    with urllib.request.urlopen(req, timeout=25) as r:
        roh = r.read(3_000_000).decode("utf-8", "replace")
    # Rezept-Daten, die viele Seiten maschinenlesbar mitliefern (schema.org/Recipe)
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', roh, re.S | re.I):
        try:
            j = json.loads(block.strip())
        except ValueError:
            continue
        kandidaten = j if isinstance(j, list) else (j.get("@graph") or [j]) if isinstance(j, dict) else []
        for k in kandidaten:
            typ = k.get("@type") if isinstance(k, dict) else None
            if typ == "Recipe" or (isinstance(typ, list) and "Recipe" in typ):
                return "Rezept-Daten der Seite: " + json.dumps({x: k.get(x) for x in ("name", "recipeYield", "totalTime", "recipeIngredient",
                                                                                       "recipeInstructions", "description")}, ensure_ascii=False)[:15000]
    titel = re.search(r"<title[^>]*>(.*?)</title>", roh, re.S | re.I)
    roh = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", roh)
    text = re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", roh))).strip()
    return f"Seite: {titel.group(1).strip() if titel else url}\n{text[:15000]}"


def foto_b64(pfad):
    if not os.path.realpath(pfad).startswith("/media/eingang/"):
        raise ValueError("Foto-Pfad nicht erlaubt")
    with open(pfad, "rb") as f:
        roh = f.read()
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(roh)).convert("RGB")
        img.thumbnail((1800, 1800))
        p = io.BytesIO()
        img.save(p, "JPEG", quality=85)
        roh = p.getvalue()
    except Exception:  # noqa: BLE001
        pass
    return base64.b64encode(roh).decode("ascii")


def rezept_machen(auftrag):
    d = daten_laden()
    e = d["einstellungen"]
    inhalt = []
    quelle = ""
    if auftrag.get("url"):
        quelle = auftrag["url"]
        status(True, "Rezept wird von der Seite geholt …", art="rezept")
        try:
            text = seite_holen(auftrag["url"])
        except Exception as fehler:  # noqa: BLE001
            raise RuntimeError(f"Die Seite ließ sich nicht öffnen ({type(fehler).__name__}). Bei Instagram/TikTok/YouTube: "
                               "Rezepttext kopieren und schicken.")
        inhalt.append({"type": "text", "text": text})
    for pfad in auftrag.get("fotos") or []:
        inhalt.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": foto_b64(pfad)}})
        quelle = quelle or "Foto"
    if auftrag.get("text"):
        inhalt.append({"type": "text", "text": "Unser Text: " + str(auftrag["text"])[:12000]})
        quelle = quelle or "Text"
    if not inhalt:
        raise ValueError("Kein Rezept mitgeschickt")
    inhalt.append({"type": "text", "text":
                   f"Mach daraus ein sauberes Rezept auf Deutsch für {portionen(e)} Portionen (Mengen umrechnen), ohne Werbung und "
                   f"Geschichten. Allergien/Ernährung beachten und, falls nötig, im Feld notiz sagen, was man ersetzen sollte: "
                   f"{', '.join(e.get('allergien') or []) or 'keine'}, {e.get('ernaehrung') or 'keine'}.\n"
                   "Antworte NUR mit JSON: {\"titel\", \"kurz\", \"portionen\", \"zeit_min\", \"zutaten\": [...], \"schritte\": [...], "
                   "\"notiz\": \"\", \"kategorie\": \"z. B. Nudeln, Suppe, Fleisch, Fisch, Vegetarisch, Kuchen, Salat\"} "
                   "– zutaten und schritte wie hier: " + GERICHT_FORMAT})
    status(True, "Claude schreibt das Rezept …", art="rezept")
    r = claude(GRUND, inhalt, max_tokens=6000, effort="low")
    if not r.get("titel") or not r.get("zutaten"):
        raise RuntimeError("Darin habe ich kein Kochrezept gefunden. (Ist es ein Rezept vom Arzt? Dann bitte mit dem Text "
                           "„Beleg“ schicken, das kommt in die Akte.)")
    rezept = {"id": uuid.uuid4().hex[:8], "titel": str(r["titel"])[:80], "kurz": str(r.get("kurz") or "")[:200],
              "portionen": int(float(r.get("portionen") or portionen(e))), "zeit_min": int(float(r.get("zeit_min") or 0)),
              "zutaten": zutaten_sauber(r.get("zutaten")), "schritte": schritte_sauber(r.get("schritte")),
              "notiz": str(r.get("notiz") or "")[:300], "kategorie": str(r.get("kategorie") or "")[:30],
              "quelle": quelle[:300], "favorit": False, "erstellt": date.today().isoformat()}
    with Sperre():
        d = daten_laden()
        d["rezepte"].append(rezept)
        if auftrag.get("datum"):
            g = dict(rezept, art="kochen", rezept_id=rezept["id"], grund="Wunsch")
            d["plan"][auftrag["datum"]] = gericht_sauber(g)
        json_schreiben(DATEN, d)
    return (f"Rezept gespeichert: {rezept['titel']} ({rezept['zeit_min']} min, {len(rezept['zutaten'])} Zutaten)"
            + (f" und für {de(date.fromisoformat(auftrag['datum']))} eingeplant" if auftrag.get("datum") else "")
            + ". Zu finden in der Küche unter „Rezepte“." + (f"\nHinweis: {rezept['notiz']}" if rezept["notiz"] else ""))


ARBEIT = {"plan": plan_machen, "tausch": tausch_machen, "rezept": rezept_machen}


def im_hintergrund(auftrag):
    if os.fork() > 0:
        return
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    fd = os.open(os.devnull, os.O_RDWR)
    for s in (0, 1, 2):
        os.dup2(fd, s)
    chats = [c for c in [auftrag.get("chat")] + list(auftrag.get("chats") or []) if c]
    try:
        text = ARBEIT[auftrag["art"]](auftrag)
        status(False, text, art=auftrag["art"])
        for c in chats:
            senden(c, "🍽 " + text + (auftrag.get("nachsatz") or ""))
    except LeiseFertig:
        status(False, "", art=auftrag.get("art", ""))
    except Exception as fehler:  # noqa: BLE001
        meldung = str(fehler)[:250] if isinstance(fehler, (RuntimeError, ValueError)) else f"{type(fehler).__name__}: {str(fehler)[:200]}"
        status(False, "", fehler=meldung, art=auftrag.get("art", ""))
        for c in chats[:1]:
            senden(c, "⚠️ Küche: " + meldung)
    os._exit(0)


def senden(chat, text):
    try:
        import akte
        akte.senden(chat, text)
    except Exception:  # noqa: BLE001
        pass


# ---------- schnelle Aufrufe ----------

def speichern(teile):
    neu = json.loads(base64.b64decode("".join(teile)).decode("utf-8"))
    if not isinstance(neu, dict) or not isinstance(neu.get("einstellungen"), dict) or not isinstance(neu.get("plan"), dict):
        raise ValueError("unerwartetes Format")
    if json_laden(STATUS, {}).get("laeuft") and time.time() - os.path.getmtime(STATUS) < 400:
        raise RuntimeError("Claude arbeitet gerade am Plan – gleich nochmal speichern")
    with Sperre():
        if os.path.exists(DATEN):
            import shutil
            shutil.copy2(DATEN, DATEN.replace(".json", ".vorher.json"))
        json_schreiben(DATEN, neu)
    return {"ok": True}


def stand():
    d = daten_laden()
    heute = date.today()
    woche = []
    for i in range(-1, 8):
        tag = heute + timedelta(days=i)
        g = (d.get("plan") or {}).get(tag.isoformat())
        if g:
            woche.append({"datum": tag.isoformat(), "tag": TAGE[tag.weekday()][:2], "text": g.get("titel", ""), "art": g.get("art", ""),
                          "zeit": g.get("zeit_min", 0)})
    h = (d.get("plan") or {}).get(heute.isoformat()) or {}
    hinweis = ""
    if h.get("art") == "kochen" and h.get("zeit_min"):
        hinweis = f"ca. {h['zeit_min']} min"
    if h.get("art") == "reste":
        hinweis = "Reste aufwärmen"
    morgen = (d.get("plan") or {}).get((heute + timedelta(days=1)).isoformat()) or {}
    return {"gericht": h.get("titel", ""), "hinweis": hinweis, "grund": h.get("grund", ""), "morgen": morgen.get("titel", ""),
            "woche": woche, "rezepte": len(d.get("rezepte") or []), "vorrat": [x.get("name") for x in d.get("vorrat") or []][:20],
            "eingerichtet": bool(d["einstellungen"].get("eingerichtet")), "laeuft": json_laden(STATUS, {}).get("laeuft", False)}


def zahl_text(v):
    if v is None:
        return ""
    return str(int(v)) if abs(v - round(v)) < 0.01 else f"{v:.1f}".replace(".", ",")


def einkauf(auftrag):
    """Zutaten der Tage von–bis zusammenrechnen (gleicher Name + Einheit), Basis-Zutaten und Vorrat weglassen."""
    d = daten_laden()
    von, bis = auftrag.get("von") or date.today().isoformat(), auftrag.get("bis") or (date.today() + timedelta(days=6)).isoformat()
    vorrat = [str(x.get("name", "")).lower() for x in d.get("vorrat") or []]
    summe = {}
    for k, g in sorted((d.get("plan") or {}).items()):
        if not (von <= k <= bis) or g.get("art") != "kochen":
            continue
        for z in g.get("zutaten") or []:
            name = z.get("name", "")
            if z.get("basis") or any(v and (v in name.lower() or name.lower() in v) for v in vorrat):
                continue
            key = (name.lower(), z.get("einheit", ""))
            s = summe.setdefault(key, {"name": name, "einheit": z.get("einheit", ""), "menge": 0.0, "ohne_menge": False,
                                       "bereich": z.get("bereich", "Sonstiges"), "fuer": []})
            if z.get("menge") is None:
                s["ohne_menge"] = True
            else:
                s["menge"] += float(z["menge"])
            s["fuer"].append(f"{TAGE[date.fromisoformat(k).weekday()][:2]} {g.get('titel', '')}")
    liste = []
    for s in sorted(summe.values(), key=lambda s: (BEREICHE.index(s["bereich"]) if s["bereich"] in BEREICHE else 99, s["name"])):
        menge = zahl_text(s["menge"]) if s["menge"] else ""
        einheit = s["einheit"]
        if einheit == "g" and s["menge"] >= 1000:
            menge, einheit = zahl_text(s["menge"] / 1000), "kg"
        if einheit == "ml" and s["menge"] >= 1000:
            menge, einheit = zahl_text(s["menge"] / 1000), "l"
        text = " ".join(x for x in (menge, einheit, s["name"]) if x)
        liste.append({"text": text, "notiz": "für " + ", ".join(dict.fromkeys(s["fuer"])), "bereich": s["bereich"]})
    return {"liste": liste, "von": von, "bis": bis}


TELEGRAM = GRUND + """

Jetzt schreibt dir jemand aus der Familie per Telegram zum Thema Essen. Du siehst unseren Essensplan, die Rezepte und den Vorrat.
Antworte NUR mit JSON:
{"antwort": "kurze, freundliche Antwort für Telegram (ohne Markdown, höchstens 8 Zeilen)",
 "aktionen": [
   {"art": "planen", "von": "JJJJ-MM-TT", "tage": 7, "wunsch": ""}            – ganze Woche/mehrere Tage neu planen lassen
   {"art": "tag", "datum": "JJJJ-MM-TT", "wunsch": "Lasagne"}                 – an einem Tag ein bestimmtes Gericht (Rezept wird erstellt)
   {"art": "tag_rezept", "datum": "JJJJ-MM-TT", "rezept_id": "…"}             – gespeichertes Rezept an einem Tag einplanen
   {"art": "frei", "datum": "JJJJ-MM-TT", "titel": "Auswärts essen"}          – an dem Tag wird nicht gekocht
   {"art": "gekocht", "datum": "JJJJ-MM-TT"}
   {"art": "vorrat", "name": "Kürbis", "menge": "3 Stück", "quelle": "ernte"|"vorrat"}   – Ernte/Vorrat eintragen
   {"art": "vorrat_weg", "name": "Kürbis"}                                    – verbraucht/aufgebraucht
   {"art": "rezept", "url": "https://…", "text": "", "datum": ""}           – Rezept aus Link oder Text speichern (optional einplanen)
   {"art": "einkauf", "von": "JJJJ-MM-TT", "bis": "JJJJ-MM-TT"}              – Zutaten auf die Einkaufsliste
   {"art": "einstellung", "feld": "arbeitszeiten" | "hinweise", "text": "…"} – feste Wochenzeiten (Arbeit, Schule, Chor,
       Training) bzw. Vorlieben merken; text = der KOMPLETTE neue Inhalt des Feldes (Bisheriges übernehmen, Neues ergänzen
       oder ersetzen), übersichtlich je Person und Wochentag
 ]}
Regeln: Fragen ("Was gibt's heute/morgen/diese Woche?", "Wie lange braucht das?", "Was brauche ich für …?") nur beantworten,
aktionen leer. "Ernte: …", "Wir haben … geerntet" → vorrat mit quelle "ernte". Ein Link → rezept. Bei "planen", "tag" und "rezept"
sag in der Antwort, dass Claude kurz daran arbeitet und gleich eine Nachricht kommt. Relative Tage ("Samstag", "morgen") in
Datum umrechnen. Nichts erfinden, was nicht im Plan steht."""


def telegram(auftrag):
    d = daten_laden()
    heute = date.today()
    plan = "\n".join(f"{de(date.fromisoformat(k))} ({k}): {v.get('art')} – {v.get('titel')} ({v.get('zeit_min', '?')} min)"
                     + (f"; Zutaten: {', '.join(z.get('name', '') for z in v.get('zutaten') or [])}" if v.get("zutaten") else "")
                     for k, v in sorted((d.get("plan") or {}).items()) if (heute - timedelta(days=2)).isoformat() <= k <= (heute + timedelta(days=13)).isoformat())
    rezepte = "; ".join(f"{r['id']}: {r.get('titel')}{' (Liebling)' if r.get('favorit') else ''}" for r in d.get("rezepte") or [])[:3000]
    frage = (f"Heute ist {de(heute)} {heute.year} ({heute.isoformat()}), {datetime.now().strftime('%H:%M')} Uhr.\n"
             f"Essensplan:\n{plan or '(noch nichts geplant)'}\n\nGespeicherte Rezepte: {rezepte or 'keine'}\n"
             f"Vorrat/Ernte: {vorrat_text(d) or 'nichts eingetragen'}\n"
             f"Gespeicherte Arbeitszeiten/feste Termine: {d['einstellungen'].get('arbeitszeiten') or '(leer)'}\n"
             f"Gespeicherte Vorlieben: {d['einstellungen'].get('hinweise') or '(leer)'}\n"
             f"Termine: {termine_text(auftrag.get('termine'), heute, heute + timedelta(days=13)) or 'keine'}\n\n"
             f"Nachricht von {auftrag.get('von') or 'der Familie'}: {auftrag.get('text', '')}")
    a = claude(TELEGRAM, frage, max_tokens=2500, effort="low", timeout=45)
    folge = []
    with Sperre():
        d = daten_laden()
        for x in a.get("aktionen") or []:
            if not isinstance(x, dict):
                continue
            art = x.get("art")
            dat = str(x.get("datum", ""))
            gueltig = re.match(r"^\d{4}-\d\d-\d\d$", dat) is not None
            if art == "vorrat" and x.get("name"):
                d["vorrat"] = [v for v in d["vorrat"] if str(v.get("name", "")).lower() != str(x["name"]).lower()]
                d["vorrat"].append({"name": str(x["name"])[:40], "menge": str(x.get("menge") or "")[:30],
                                    "quelle": "ernte" if x.get("quelle") == "ernte" else "vorrat", "seit": heute.isoformat()})
            elif art == "vorrat_weg" and x.get("name"):
                d["vorrat"] = [v for v in d["vorrat"] if str(x["name"]).lower() not in str(v.get("name", "")).lower()]
            elif art == "frei" and gueltig:
                d["plan"][dat] = {"art": "frei", "titel": str(x.get("titel") or "Nicht kochen")[:60], "grund": "per Telegram"}
            elif art == "gekocht" and gueltig and dat in d["plan"]:
                d["plan"][dat]["gekocht"] = True
            elif art == "tag_rezept" and gueltig:
                r = next((r for r in d["rezepte"] if r.get("id") == x.get("rezept_id")), None)
                if r:
                    d["plan"][dat] = gericht_sauber(dict(r, art="kochen", rezept_id=r["id"], grund="Wunsch"))
            elif art == "einstellung" and x.get("feld") in ("arbeitszeiten", "hinweise") and str(x.get("text", "")).strip():
                d["einstellungen"][x["feld"]] = str(x["text"]).strip()[:1500]
            elif art in ("planen", "tag", "rezept", "einkauf"):
                folge.append(x)
        json_schreiben(DATEN, d)
    return {"antwort": str(a.get("antwort") or "Erledigt.")[:1500], "folge": folge}


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else "stand"
    if aktion == "speichern":
        print(json.dumps(speichern(sys.argv[2:])))
        return
    if aktion == "stand":
        print(json.dumps(stand(), ensure_ascii=False))
        return
    # lange Aufträge (Foto von der Küchen-Seite) kommen in Stücken
    auftrag = json.loads(base64.b64decode("".join(sys.argv[2:])).decode("utf-8")) if len(sys.argv) > 2 and sys.argv[2] else {}
    if aktion == "einkauf":
        print(json.dumps(einkauf(auftrag), ensure_ascii=False))
    elif aktion == "telegram":
        print(json.dumps(telegram(auftrag), ensure_ascii=False))
    elif aktion == "ki":
        if auftrag.get("art") not in ARBEIT:
            raise ValueError("unbekannte Arbeit")
        alt = json_laden(STATUS, {})
        if alt.get("laeuft") and time.time() - os.path.getmtime(STATUS) < 400:
            raise RuntimeError("Claude arbeitet schon – bitte kurz warten")
        # Fotos von der Küchen-Seite als Datei ablegen (wie Fotos aus Telegram)
        for i, b in enumerate(auftrag.pop("bilder", None) or []):
            os.makedirs("/media/eingang", exist_ok=True)
            pfad = f"/media/eingang/rezept_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}.jpg"
            with open(pfad, "wb") as f:
                f.write(base64.b64decode(b))
            auftrag.setdefault("fotos", []).append(pfad)
        status(True, "Claude legt los …", art=auftrag["art"])
        im_hintergrund(auftrag)
        print(json.dumps({"ok": True, "gestartet": auftrag["art"]}))
    else:
        raise ValueError("unbekannte Aktion")


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        meldung = str(fehler)[:250] if isinstance(fehler, (RuntimeError, ValueError)) else f"{type(fehler).__name__}: {str(fehler)[:200]}"
        print(json.dumps({"ok": False, "fehler": meldung}, ensure_ascii=False))
