#!/usr/bin/env python3
"""Garten-Fragen und Foto-Check mit Claude (Aufruf aus script.garten_ki).

Argument 1: Base64 des JSON {art: "foto"|"frage"|"chat", frage, pflanze, beet, bereich, wetter, plan, quelle,
            schluessel (bei "chat": was gerade als erledigt gemeldet werden kann, aus sensor.garten_aufgaben),
            datei (Foto-Pfad, z. B. von Telegram), plan_laden (Plan aus garten_daten.json lesen), merken (Ergebnis in den Foto-Verlauf)}.
Argument 2 ff. (optional): das Foto als Base64-JPEG, in Stücke geteilt.
Der API-Schlüssel kommt aus der Anthropic-Integration von Home Assistant (.storage), nicht aus dem Repository.
"chat" = Fragen oder Meldungen vom Monitor bzw. der Garten-Seite ("Kürbis habe ich geerntet"): Claude
antwortet und merkt sich Erledigtes und Notizen in /config/www/garten_erledigt.json; der Verlauf steht in
/config/www/garten_fragen.json (beides lokal, nicht im Repository).
Ausgabe immer JSON: {"ok": true, "text": "..."} oder {"ok": false, "fehler": "..."}.
"""
import base64
import io
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

DATEN = "/config/www/garten_daten.json"
ERLEDIGT = "/config/www/garten_erledigt.json"
FRAGEN = "/config/www/garten_fragen.json"

MODELL = "claude-opus-5-5"

SYSTEM = """Du bist ein erfahrener Gemüsegärtner und berätst eine Familie in Norddeutschland (Niedersachsen, Klima ähnlich Bremen/Oldenburg).
Sie haben einen selbstgebauten überdachten Gemüsegarten: Holzständer mit lichtdurchlässigem Folien-Dach und einem Lattenzaun
rundherum – also KEIN geschlossenes Gewächshaus. Er ist offen und unbeheizt, dort ist es kaum wärmer als draußen und genauso
frostig, aber kein Regen kommt an (Regenschutz, Blätter bleiben trocken). Darin umlaufende Hochbeete mit Tropfschlauch-Bewässerung.
Draußen im Garten haben sie drei angehäufelte Erdstreifen (ca. 60 cm breit, 25 cm hoch).
Antworte auf Deutsch, freundlich, konkret und kurz – so, dass ein Laie es sofort umsetzen kann.
Gliedere mit kurzen Zwischenzeilen, z. B. "Zustand:", "Was ich sehe:", "Was jetzt tun:", "Gießen/Düngen:".
Berücksichtige das mitgeschickte Wetter und die Jahreszeit. Nenne Mengen (Liter, Zentimeter, Tage), wo es hilft.
Wenn du auf dem Foto etwas nicht sicher erkennen kannst, sag das ehrlich und nenne, worauf sie achten sollen.
Keine Markdown-Tabellen, keine Überschriften mit #, höchstens einfache Aufzählungen mit "- "."""


CHAT = """

So antwortest du hier: Die Familie schreibt dir am Monitor oder auf der Garten-Seite – entweder eine Frage
("Kann Rhabarber draußen stehen?") oder eine Meldung, was erledigt ist ("Kürbis habe ich schon geerntet",
"Kartoffeln liegen zum Vorkeimen"), oder beides. Antworte NUR mit einem JSON-Objekt, ohne Text davor oder danach:
{"antwort": "kurze, freundliche Antwort (bei Meldungen 1–2 Sätze mit einem passenden Tipp, bei Fragen höchstens ca. 8 Sätze)",
 "erledigt": [{"key": "<key aus der Liste 'Meldbar'>", "dauer": "heute" | "woche" | "2wochen" | "saison"}],
 "zurueck": ["<key>", …nur wenn sie sagen, dass etwas doch NICHT erledigt ist, sonst leer],
 "notiz": "was man sich für später merken sollte (z. B. 'Rhabarber steht am Erdhaufen am Weg'), sonst leer"}
Regeln für "erledigt": nur Keys aus der Liste "Meldbar" nehmen, nichts erfinden. Ganz abgeerntet/abgeräumt → "ernte:<pflanze>"
mit "saison"; nur ein Teil geerntet, es kommt noch mehr → "ernten:<pflanze>" mit "woche". Gegossen → "heute".
Gesät/gepflanzt/vorgezogen/gekauft/vorgekeimt/gelegt → "saison". Angehäufelt → "2wochen" (danach nochmal).
Herbst- oder Frühjahrsarbeit erledigt → "saison". Ist es nur eine Frage, bleibt "erledigt" leer."""


HAUS = """Du bist ein erfahrener Haustechniker und Hausmeister und hilfst einer Familie in Norddeutschland bei der Wartung
ihres Resthofs (Haus mit Wärmepumpe, Kamin mit Wassertasche, Pufferspeicher, Solaranlage, Regenwasser-Zisterne, Kleinkläranlage,
Nebengebäude mit Werkstatt, Maschinen, Wohnwagen). Erkläre konkret und Schritt für Schritt, so dass ein Laie es sicher umsetzen kann:
was man braucht (Werkzeug, Material mit Menge), die einzelnen Handgriffe, worauf man achten muss und woran man erkennt, dass es
richtig ist. Nutze die Angaben aus dem Haus-Handbuch (Gerätetypen, Sicherungen, Standorte), wenn sie passen, und nenne sie.
Sicherheit zuerst: Bei Arbeiten an Strom (außer Testtaste/Sicherung schalten), Gas, Kältemittel, Abgas oder auf hohen Leitern
klar sagen, wann der Fachbetrieb ran muss. Wenn du etwas über die konkrete Anlage nicht sicher weißt, sag das ehrlich und
sag, wo es steht (Typenschild, Anleitung). Antworte auf Deutsch, freundlich, ohne Markdown-Tabellen und ohne Überschriften
mit #, höchstens einfache Aufzählungen mit "- " oder "1." und kurze Zwischenzeilen wie "Du brauchst:", "So geht's:", "Achtung:"."""

HANDBUCH = "/config/wartung_handbuch.txt"


def handbuch_text(link):
    """Seiten des Haus-Handbuchs (Haustechnik, Geräte, Maschinen, Wohnwagen) als Text – einmal am Tag neu geholt."""
    try:
        if os.path.getmtime(HANDBUCH) > datetime.now().timestamp() - 86400:
            with open(HANDBUCH, encoding="utf-8") as f:
                return f.read()
    except OSError:
        pass
    if not re.match(r"^https?://", link or ""):
        return ""
    import html as html_mod
    import urllib.parse
    import urllib.request
    basis = link if link.endswith("/") or link.rsplit("/", 1)[-1].count(".") else link + "/"
    teile = []
    for seite in ("haustechnik.html", "geraete.html", "maschinen.html", "wohnwagen.html", "sicherungen.html"):
        try:
            req = urllib.request.Request(urllib.parse.urljoin(basis, seite), headers={"User-Agent": "HomeAssistant-Wartung"})
            with urllib.request.urlopen(req, timeout=8) as r:
                roh = r.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 – dann ohne diese Seite
            continue
        roh = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", roh)
        text = re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", roh))).strip()
        teile.append(f"[{seite}] {text[:9000]}")
    text = "\n".join(teile)[:30000]
    try:
        with open(HANDBUCH, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    return text


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


def notizen_text():
    n = json_laden(ERLEDIGT, {}).get("notizen", [])[-15:]
    return "; ".join(f"{x.get('datum', '')}: {x.get('text', '')}" for x in n if isinstance(x, dict))


def chat_merken(auftrag, roh):
    """Claudes JSON-Antwort auswerten: Erledigtes und Notizen speichern, Verlauf schreiben."""
    treffer = re.search(r"\{.*\}", roh, re.S)
    try:
        a = json.loads(treffer.group(0)) if treffer else {}
    except ValueError:
        a = {}
    antwort = str(a.get("antwort") or "").strip() or roh.strip()
    texte = {k.get("key"): k.get("text", "") for k in auftrag.get("schluessel") or [] if isinstance(k, dict)}
    erlaubt = set(texte)
    heute = date.today()
    tage = {"heute": 0, "woche": 6, "2wochen": 13}
    e = json_laden(ERLEDIGT, {})
    liste = [x for x in e.get("erledigt", []) if isinstance(x, dict) and str(x.get("bis", "")) >= heute.isoformat()]
    gemeldet = []
    for x in a.get("erledigt") or []:
        key = str((x or {}).get("key", "")) if isinstance(x, dict) else ""
        if key not in erlaubt:
            continue
        dauer = x.get("dauer", "saison")
        bis = date(heute.year, 12, 31) if dauer not in tage else heute + timedelta(days=tage[dauer])
        liste = [y for y in liste if y.get("key") != key]
        liste.append({"key": key, "bis": bis.isoformat(), "datum": heute.isoformat(), "text": auftrag.get("frage", "")[:200]})
        gemeldet.append(key)
    for key in a.get("zurueck") or []:
        if isinstance(key, str) and any(y.get("key") == key for y in liste):
            liste = [y for y in liste if y.get("key") != key]
            gemeldet.append("-" + key)
    e["erledigt"] = liste
    notiz = str(a.get("notiz") or "").strip()
    if notiz:
        e["notizen"] = (e.get("notizen", []) + [{"datum": heute.strftime("%d.%m.%Y"), "text": notiz[:300]}])[-40:]
    json_schreiben(ERLEDIGT, e)
    verlauf = json_laden(FRAGEN, [])
    verlauf.append({"zeit": datetime.now().strftime("%d.%m.%Y %H:%M"), "quelle": auftrag.get("quelle", ""),
                    "frage": auftrag.get("frage", "")[:500], "antwort": antwort,
                    "erledigt": [("nicht mehr erledigt: " + texte.get(k[1:], k[1:])) if k.startswith("-") else texte.get(k, k) for k in gemeldet]})
    json_schreiben(FRAGEN, verlauf[-30:])
    return antwort, gemeldet


def api_schluessel():
    with open("/config/.storage/core.config_entries", encoding="utf-8") as f:
        eintraege = json.load(f)["data"]["entries"]
    for e in eintraege:
        if e.get("domain") == "anthropic" and not e.get("disabled_by"):
            schluessel = (e.get("data") or {}).get("api_key")
            if schluessel:
                return schluessel
    raise RuntimeError("Keine Anthropic-Integration mit API-Schlüssel gefunden")


def plan_aus_datei():
    """Kurzfassung des Pflanzplans aus garten_daten.json (für Fotos per Telegram)."""
    try:
        with open(DATEN, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return ""
    info = d.get("info") or {}
    beete = {b["id"]: b.get("name", "") for b in (d.get("karte") or {}).get("beete", [])}
    beete.update({k: v.get("name", "") for k, v in (info.get("beete") or {}).items() if v.get("name")})
    namen = {k: v.get("name", k) for k, v in (info.get("pflanzen") or {}).items()}
    return "; ".join(f"{p.get('saison', '')} {beete.get(p.get('beet'), 'Hochbeet unter dem Dach' if str(p.get('beet', '')).startswith('gh-') else 'Beet')}: "
                     f"{namen.get(p.get('pflanze'), p.get('pflanze', ''))} {p.get('anzahl', '')}×"
                     for p in d.get("pflanzungen", []))[:1500]


def foto_laden(pfad):
    """Foto lesen, zu große Bilder verkleinern (Pillow ist in Home Assistant vorhanden)."""
    if not os.path.realpath(pfad).startswith("/config/garten_fotos/"):
        raise ValueError("Foto-Pfad nicht erlaubt")
    with open(pfad, "rb") as f:
        roh = f.read()
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(roh)).convert("RGB")
        img.thumbnail((1600, 1600))
        puffer = io.BytesIO()
        img.save(puffer, "JPEG", quality=85)
        roh = puffer.getvalue()
    except Exception:  # noqa: BLE001 – dann eben das Original schicken
        pass
    return base64.b64encode(roh).decode("ascii")


def vorschaubild(b64):
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        img.thumbnail((140, 140))
        puffer = io.BytesIO()
        img.save(puffer, "JPEG", quality=55)
        return base64.b64encode(puffer.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001
        return ""


def merken(auftrag, text, bild):
    """Ergebnis in den Foto-Verlauf der Garten-Seite schreiben."""
    try:
        with open(DATEN, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(d, dict) or not isinstance(d.get("karte"), dict):
        return
    fotos = d.setdefault("fotos", [])
    fotos.append({"datum": datetime.now().strftime("%d.%m.%Y"), "pflanze": auftrag.get("pflanze", ""), "beet": "",
                  "frage": auftrag.get("frage", ""), "text": text, "bild": vorschaubild(bild) if bild else "", "quelle": "Telegram"})
    d["fotos"] = fotos[-20:]
    tmp = DATEN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, DATEN)


def main():
    auftrag = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
    bild = "".join(sys.argv[2:]).strip()
    if not bild and auftrag.get("datei"):
        bild = foto_laden(auftrag["datei"])
    if auftrag.get("plan_laden") and not auftrag.get("plan"):
        auftrag["plan"] = plan_aus_datei()
    try:
        import anthropic
    except ImportError:
        print(json.dumps({"ok": False, "fehler": "Die Anthropic-Bibliothek fehlt in Home Assistant"}))
        return

    kontext = []
    if auftrag.get("bereich") or auftrag.get("beet"):
        kontext.append(f"Ort: {auftrag.get('bereich', '')} – {auftrag.get('beet', '')}".strip(" –"))
    if auftrag.get("pflanze"):
        kontext.append(f"Pflanze laut Plan: {auftrag['pflanze']}")
    if auftrag.get("wetter"):
        kontext.append(f"Wetter: {auftrag['wetter']}")
    if auftrag.get("plan"):
        kontext.append(f"Aktueller Pflanzplan: {auftrag['plan']}")
    if auftrag.get("art") == "chat" or auftrag.get("plan_laden"):
        notizen = notizen_text()
        if notizen:
            kontext.append(f"Unsere Notizen von früher: {notizen}")
    if auftrag.get("art") == "chat":
        aufgaben = auftrag.get("aufgaben") or []
        if aufgaben:
            kontext.append("Aufgaben, die gerade auf dem Monitor stehen: " + "; ".join(f"{x.get('titel', '')} {x.get('text', '')}".strip() for x in aufgaben if isinstance(x, dict)))
        kontext.append("Meldbar (key = Bedeutung): " + "; ".join(f"{x.get('key')} = {x.get('text')}" for x in auftrag.get("schluessel") or [] if isinstance(x, dict)))
        schon = [x.get("key") for x in json_laden(ERLEDIGT, {}).get("erledigt", []) if isinstance(x, dict) and str(x.get("bis", "")) >= date.today().isoformat()]
        if schon:
            kontext.append("Schon als erledigt gemerkt: " + ", ".join(schon))
        vorher = json_laden(FRAGEN, [])[-3:]
        if vorher:
            kontext.append("Unser letztes Gespräch: " + " | ".join(f"Wir: {x.get('frage', '')} – Du: {x.get('antwort', '')[:300]}" for x in vorher))
    if auftrag.get("art") == "wartung":
        a = auftrag.get("aufgabe") or {}
        kontext.append(f"Wartungsaufgabe: {a.get('titel', '')} (Bereich {a.get('bereich', '')}, alle {a.get('intervall', '?')} Monate)")
        if a.get("hinweis"):
            kontext.append(f"Hinweis aus dem Handbuch: {a['hinweis']}")
        if a.get("zuletzt"):
            kontext.append(f"Zuletzt erledigt: {a['zuletzt']}")
        hb = handbuch_text(auftrag.get("link", ""))
        if hb:
            kontext.append("Auszug aus unserem Haus-Handbuch (Geräte, Technik, Sicherungen):\n" + hb)
        for x in (auftrag.get("verlauf") or [])[-4:]:
            if isinstance(x, dict):
                kontext.append(f"Vorher gefragt: {x.get('frage', '')} – deine Antwort: {str(x.get('antwort', ''))[:1200]}")
    kontext.append(f"Datum: {auftrag.get('datum') or date.today().strftime('%d.%m.%Y')}")
    frage = (auftrag.get("frage") or "").strip()
    if auftrag.get("art") == "foto":
        frage = frage or "Geht es der Pflanze gut? Was soll ich tun?"
        text = "Bitte schau dir das Foto aus unserem Garten an.\n" + "\n".join(kontext) + f"\n\nUnsere Frage: {frage}"
    else:
        text = "\n".join(kontext) + f"\n\nUnsere Frage: {frage}"

    inhalt = []
    if bild:
        inhalt.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": bild}})
    inhalt.append({"type": "text", "text": text})

    client = anthropic.Anthropic(api_key=api_schluessel(), timeout=55, max_retries=1)
    antwort = client.messages.create(
        model=MODELL,
        max_tokens=3000,
        system=HAUS if auftrag.get("art") == "wartung" else SYSTEM + (CHAT if auftrag.get("art") == "chat" else ""),
        messages=[{"role": "user", "content": inhalt}],
        # schnelle, alltagstaugliche Antwort (Home Assistant wartet höchstens 60 Sekunden);
        # lehnt das Modell ab, springt automatisch ein passendes anderes Modell ein
        extra_body={"output_config": {"effort": "low"}, "fallbacks": "default"},
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
    )
    if antwort.stop_reason == "refusal":
        print(json.dumps({"ok": False, "fehler": "Claude hat die Anfrage abgelehnt"}))
        return
    ergebnis = "".join(b.text for b in antwort.content if getattr(b, "type", "") == "text").strip()
    if auftrag.get("art") == "chat":
        text, gemeldet = chat_merken(auftrag, ergebnis)
        print(json.dumps({"ok": True, "text": text, "erledigt": gemeldet}, ensure_ascii=False))
        return
    if auftrag.get("merken"):
        merken(auftrag, ergebnis, bild)
    print(json.dumps({"ok": True, "text": ergebnis}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": f"{type(fehler).__name__}: {fehler}"[:300]}, ensure_ascii=False))
