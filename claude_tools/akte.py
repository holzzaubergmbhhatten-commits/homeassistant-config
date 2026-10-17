#!/usr/bin/env python3
"""Digitale Akte: Belege, Rechnungen, Versicherungen, Verträge, Bescheide – per Telegram hinein, per Telegram wieder heraus.

Ablauf (packages/akte.yaml):
  akte.py neu <base64-JSON {datei, chat, von, text}>
      Foto (JPG) oder PDF aus Telegram. Fotos werden verkleinert und als PDF abgelegt. Claude liest den Beleg und trägt
      Art, Absender, Datum, Betrag, Person, Steuer, "bei der Versicherung einreichen" und Fristen ein. Antwort per Telegram.
      Text "+" / "weiter" / "Seite 2" zum Foto: als weitere Seite an den letzten Beleg (gleicher Chat, letzte Stunde).
  akte.py befehl <base64-JSON {text, chat}>
      "Akte …" / "Beleg …" (Frage oder Suche), "Steuer 2026", "Einreichen", "Eingereicht [Nummern]", "Fristen", "Akte Hilfe"
  akte.py erinnerung <base64-JSON {chats: [...], art: "fristen"|"einreichen"}>

Alles, was länger dauert, läuft im Hintergrund weiter (Home Assistant wartet höchstens 60 Sekunden auf Befehle) und
antwortet selbst über den Telegram-Bot. Ablage: /config/akte_ablage/<Jahr>/…pdf, Verzeichnis: /config/akte.json – beides nur
lokal auf dem Home-Assistant-Rechner, nie im Repository. Schlüssel kommen aus den Integrationen (Anthropic, Telegram).
"""
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
import uuid
import zipfile
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import garten_ki  # noqa: E402  – Anthropic-Schlüssel und Modell

# Ablage im Konfigurationsordner: der ist in jedem Home-Assistant-Backup enthalten (der Medien-Ordner nicht immer)
ABLAGE = "/config/akte_ablage/"
SEITEN = "/config/akte_ablage/_seiten/"
EINGANG = "/media/akte/_eingang/"      # nur kurz: Download aus Telegram
EXPORT = "/media/akte/_export/"        # nur kurz: ZIP für die Steuer
ALT = "/media/akte/"                   # frühere Ablage, wird einmalig umgezogen
VERZEICHNIS = "/config/akte.json"
ZUSTAND = "/config/akte_zustand.json"   # letzte Liste je Chat (für "eingereicht 1 3")

TYPEN = ["Rechnung", "Arztrechnung", "Rezept/Verordnung", "Quittung/Kassenbon", "Versicherungspolice", "Versicherungsschreiben",
         "Erstattung/Leistungsabrechnung", "Vertrag", "Bescheid", "Lohn-/Gehaltsabrechnung", "Kontoauszug", "Garantie/Kaufbeleg",
         "Behördenpost", "Spendenquittung", "Sonstiges"]
STEUER_ARTEN = ["Krankheitskosten", "Handwerkerleistung", "Haushaltsnahe Dienstleistung", "Vorsorge/Versicherung",
                "Werbungskosten", "Spende", "Kinderbetreuung", "Vermietung", "Sonstiges", "keine"]

LESEN = f"""Du führst die digitale Akte (Belege, Rechnungen, Versicherungen, Verträge, Bescheide) einer Familie in Deutschland.
Ein Dokument kam per Telegram (Foto oder PDF, ggf. mit kurzem Text dazu). Lies es vollständig und antworte NUR mit einem
JSON-Objekt:
{{"typ": eins von {json.dumps(TYPEN, ensure_ascii=False)},
 "kategorie": "Gesundheit|Versicherung|Steuer|Haus|Fahrzeug|Vermietung|Einkauf|Arbeit|Bank|Behörde|Kinder|Sonstiges",
 "titel": "kurzer Titel, z. B. Zahnarztrechnung Implantat",
 "absender": "Firma/Praxis/Behörde",
 "datum": "JJJJ-MM-TT (Rechnungs-/Briefdatum)",
 "betrag": Zahl in Euro (Endbetrag, sonst null),
 "person": "für wen (Vorname laut Dokument, sonst leer)",
 "steuer": {{"relevant": true/false, "art": eins von {json.dumps(STEUER_ARTEN, ensure_ascii=False)}, "jahr": Jahr der Zahlung,
            "betrag": absetzbarer Teil in Euro oder null (bei Handwerkern nur Arbeits-/Fahrtkosten)}},
 "einreichen": true, wenn es eine Rechnung über Behandlung/Arznei/Hilfsmittel/Zahnarzt/Heilpraktiker ist, die man bei einer
               privaten Krankenversicherung, Beihilfe oder Zusatzversicherung zur Erstattung einreicht, sonst false,
 "fristen": [{{"datum": "JJJJ-MM-TT", "was": "z. B. Zahlung fällig / Einspruchsfrist / Kündigungsfrist / Garantie endet"}}],
 "schlagworte": ["5–10 Suchwörter, auch Synonyme"],
 "inhalt": "bei kurzen Dokumenten der vollständige wichtige Text; bei langen (Policen, Verträgen) alle wichtigen Fakten:
            Vertrags-/Versicherungsnummer, Tarif, Leistungen mit Prozent/Höchstbeträgen, Selbstbehalt, Beitrag, Laufzeit,
            Kündigung – höchstens 600 Wörter",
 "antwort": "1–2 kurze Sätze für den Chat, was abgelegt wurde (ohne Nummern und Codes)"}}
Fristen nur, wenn sie wirklich im Dokument stehen oder sich klar ergeben (Einspruch: 1 Monat nach Bescheid-Datum).
Wenn etwas unleserlich ist, lieber leer lassen als raten."""

FRAGE = """Du beantwortest Fragen zur digitalen Akte einer Familie (Belege, Versicherungen, Verträge, Bescheide).
Unten stehen passende Einträge aus dem Verzeichnis, die wichtigsten Dokumente sind angehängt. Antworte auf Deutsch, kurz und
konkret, nenne die Quelle (Titel + Datum). Steht die Antwort nicht drin, sag das ehrlich. Keine Rechts- oder Steuerberatung
erfinden. Antworte NUR mit JSON: {"antwort": "Text für Telegram", "senden": [Nummern der Einträge, die als Datei mitgeschickt
werden sollen – nur wenn danach gefragt wird ("schick mir …") oder es klar hilft, höchstens 5]}"""

HILFE = """📁 Digitale Akte – so geht's
• Beleg ablegen: Foto oder PDF an den Bot schicken. Rechnungen, Arztrechnungen, Versicherungsbriefe usw. erkennt er selbst;
  sicherheitshalber „Beleg“ als Text zum Foto schreiben.
• Mehrseitig: weitere Seiten mit dem Text „+“ hinterherschicken (innerhalb einer Stunde).
• Suchen/fragen: „Akte Was zahlt die Zahnzusatz bei Implantaten?“, „Akte schick mir die Rechnung vom Elektriker“
• Steuer: „Steuer 2026“ – Übersicht mit Summen + ZIP mit allen Belegen
• Arztrechnungen: „Einreichen“ – offene Belege als Dateien; danach „Eingereicht“ (alle) oder „Eingereicht 1 3“
• Fristen: „Fristen“ – was in den nächsten Wochen fällig ist
Erinnerung kommt automatisch: Fristen eine Woche vorher, offene Arztrechnungen am Monatsanfang."""


# ---------- Hilfen ----------

def json_laden(pfad, leer):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


def json_schreiben(pfad, d):
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, pfad)


def verzeichnis():
    d = json_laden(VERZEICHNIS, [])
    return d if isinstance(d, list) else []


def euro(x):
    try:
        return f"{float(x):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return ""


def de_datum(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return iso or ""


def sicherer_name(s, n=40):
    s = (s or "").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("Ä", "Ae").replace("Ö", "Oe")
    s = s.replace("Ü", "Ue").replace("ß", "ss")
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:n] or "Dokument"


def zeile(nr, e):
    teile = [f"{nr}. {e.get('titel') or e.get('typ')}", e.get("absender", ""), de_datum(e.get("datum")),
             euro(e.get("betrag")) if e.get("betrag") else "", e.get("person", "")]
    return " · ".join(t for t in teile if t)


# ---------- Telegram (direkt über die Bot-Schnittstelle, Token aus der Integration) ----------

def telegram_token():
    with open("/config/.storage/core.config_entries", encoding="utf-8") as f:
        for e in json.load(f)["data"]["entries"]:
            if e.get("domain") == "telegram_bot" and not e.get("disabled_by"):
                t = (e.get("data") or {}).get("api_key")
                if t:
                    return t
    raise RuntimeError("Telegram-Bot nicht gefunden")


def telegram(methode, felder, datei=None):
    import urllib.request
    url = f"https://api.telegram.org/bot{telegram_token()}/{methode}"
    if datei:
        grenze = uuid.uuid4().hex
        teile = []
        for k, v in felder.items():
            teile.append(f'--{grenze}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        name = os.path.basename(datei)
        with open(datei, "rb") as f:
            inhalt = f.read()
        teile.append(f'--{grenze}\r\nContent-Disposition: form-data; name="document"; filename="{name}"\r\n'
                     f'Content-Type: application/octet-stream\r\n\r\n'.encode() + inhalt + b"\r\n")
        teile.append(f"--{grenze}--\r\n".encode())
        req = urllib.request.Request(url, data=b"".join(teile), headers={"Content-Type": f"multipart/form-data; boundary={grenze}"})
    else:
        req = urllib.request.Request(url, data=json.dumps(felder).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def senden(chat, text):
    for i in range(0, len(text), 3900):
        telegram("sendMessage", {"chat_id": chat, "text": text[i:i + 3900], "disable_web_page_preview": True})


def datei_senden(chat, pfad, text=""):
    telegram("sendDocument", {"chat_id": chat, "caption": text[:1000]}, pfad)


# ---------- Claude ----------

def claude(system, inhalt, max_tokens=3000, effort="low"):
    import anthropic
    client = anthropic.Anthropic(api_key=garten_ki.api_schluessel(), timeout=240, max_retries=2)
    a = client.messages.create(model=garten_ki.MODELL, max_tokens=max_tokens, system=system,
                               messages=[{"role": "user", "content": inhalt}],
                               extra_body={"output_config": {"effort": effort}, "fallbacks": "default"},
                               extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"})
    if a.stop_reason == "refusal":
        raise RuntimeError("Claude hat das Dokument abgelehnt")
    roh = "".join(b.text for b in a.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", roh, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {"antwort": roh.strip()[:3000]}


def dokument_block(pfad):
    with open(pfad, "rb") as f:
        roh = f.read()
    if pfad.lower().endswith(".pdf"):
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                               "data": base64.b64encode(roh).decode("ascii")}}
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(roh).decode("ascii")}}


# ---------- Fotos → PDF ----------

def foto_verkleinern(quelle, ziel):
    from PIL import Image, ImageOps
    img = ImageOps.exif_transpose(Image.open(quelle)).convert("RGB")
    img.thumbnail((1700, 1700))
    img.save(ziel, "JPEG", quality=72, optimize=True)


def seiten_zu_pdf(seiten, ziel):
    from PIL import Image
    bilder = [Image.open(s).convert("RGB") for s in seiten]
    bilder[0].save(ziel, "PDF", resolution=150, save_all=True, append_images=bilder[1:], quality=72)


# ---------- neu ablegen ----------

def ablegen(auftrag):
    chat = auftrag.get("chat")
    quelle = auftrag.get("datei", "")
    if not os.path.realpath(quelle).startswith((EINGANG, "/media/eingang/")) or not os.path.exists(quelle):
        senden(chat, "⚠️ Akte: Datei nicht gefunden – bitte nochmal schicken.")
        return
    text = (auftrag.get("text") or "").strip()
    ist_pdf = quelle.lower().endswith(".pdf")
    liste = verzeichnis()
    os.makedirs(SEITEN, exist_ok=True)

    # weitere Seite zum letzten Foto-Beleg dieses Chats?
    eintrag = None
    if not ist_pdf and re.match(r"^\s*(\+|(weiter|seite\s*\d*|rückseite|rueckseite)\b)", text, re.I):
        grenze = (datetime.now() - timedelta(hours=1)).isoformat()
        for e in reversed(liste):
            if str(e.get("chat")) == str(chat) and e.get("seiten") and e.get("eingang", "") >= grenze:
                eintrag = e
                break
        if eintrag is None:
            senden(chat, "ℹ️ Keinen Beleg aus der letzten Stunde gefunden, an den ich die Seite hängen kann – lege sie einzeln ab.")

    if ist_pdf:
        with open(quelle, "rb") as f:
            roh = f.read()
    else:
        seite = os.path.join(SEITEN, f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg")
        foto_verkleinern(quelle, seite)
        with open(seite, "rb") as f:
            roh = f.read()
    pruef = hashlib.sha256(roh).hexdigest()
    if eintrag is None and any(e.get("sha") == pruef for e in liste):
        senden(chat, "ℹ️ Diesen Beleg habe ich schon in der Akte.")
        _weg(quelle)
        return

    if eintrag is not None:
        eintrag["seiten"].append(os.path.basename(seite))
        seiten = [os.path.join(SEITEN, s) for s in eintrag["seiten"]]
    else:
        seiten = [] if ist_pdf else [seite]

    # Claude liest das Dokument (alle Seiten)
    if ist_pdf:
        bloecke = [dokument_block(quelle)]
    else:
        bloecke = [dokument_block(s) for s in seiten]
    bloecke.append({"type": "text", "text": f"Heute: {date.today().isoformat()}\nVon: {auftrag.get('von', '')}\n"
                                            f"Text dazu: {text or '(keiner)'}"})
    e = claude(LESEN, bloecke, max_tokens=4000)

    jahr = (e.get("datum") or "")[:4] if re.match(r"^\d{4}-\d\d-\d\d$", e.get("datum") or "") else str(date.today().year)
    os.makedirs(os.path.join(ABLAGE, jahr), exist_ok=True)
    name = "_".join([e.get("datum") or date.today().isoformat(), sicherer_name(e.get("typ"), 25), sicherer_name(e.get("absender"))])
    if e.get("betrag"):
        name += "_" + sicherer_name(f"{float(e['betrag']):.2f}".replace(".", "-"), 12)
    if eintrag is not None and eintrag.get("datei"):
        _weg(os.path.join(ABLAGE, eintrag["datei"]))
    ziel_rel = os.path.join(jahr, name + ".pdf")
    n = 2
    while os.path.exists(os.path.join(ABLAGE, ziel_rel)) and (eintrag is None or eintrag.get("datei") != ziel_rel):
        ziel_rel = os.path.join(jahr, f"{name}_{n}.pdf")
        n += 1
    ziel = os.path.join(ABLAGE, ziel_rel)
    if ist_pdf:
        os.replace(quelle, ziel)
    else:
        seiten_zu_pdf(seiten, ziel)
        _weg(quelle)

    steuer = e.get("steuer") if isinstance(e.get("steuer"), dict) else {}
    neu_eintrag = eintrag or {"id": datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4], "sha": pruef,
                              "eingang": datetime.now().isoformat(timespec="seconds"), "chat": chat,
                              "von": auftrag.get("von", ""), "seiten": [] if ist_pdf else [os.path.basename(seite)]}
    alt_einreichen = (eintrag or {}).get("einreichen") or {}
    neu_eintrag.update({
        "datei": ziel_rel, "typ": e.get("typ") or "Sonstiges", "kategorie": e.get("kategorie") or "Sonstiges",
        "titel": e.get("titel") or e.get("typ") or "Dokument", "absender": e.get("absender") or "",
        "datum": e.get("datum") or "", "betrag": e.get("betrag"), "person": e.get("person") or "",
        "steuer": {"relevant": bool(steuer.get("relevant")), "art": steuer.get("art") or "keine",
                   "jahr": steuer.get("jahr") or (int(jahr) if jahr.isdigit() else None), "betrag": steuer.get("betrag")},
        "einreichen": {"noetig": bool(e.get("einreichen")), "status": alt_einreichen.get("status", "offen"),
                       "am": alt_einreichen.get("am", "")} if e.get("einreichen") else {"noetig": False},
        "fristen": [{"datum": f.get("datum"), "was": f.get("was", ""), "erinnert": False}
                    for f in (e.get("fristen") or []) if re.match(r"^\d{4}-\d\d-\d\d$", str(f.get("datum", "")))],
        "schlagworte": e.get("schlagworte") or [], "inhalt": (e.get("inhalt") or "")[:6000], "notiz": text,
    })
    if eintrag is None:
        liste.append(neu_eintrag)
    json_schreiben(VERZEICHNIS, liste)

    zeilen = [f"📁 {e.get('antwort') or 'Abgelegt.'}",
              "🗂 " + " · ".join(t for t in [neu_eintrag["typ"], neu_eintrag["absender"], de_datum(neu_eintrag["datum"]),
                                            euro(neu_eintrag["betrag"]) if neu_eintrag["betrag"] else "", neu_eintrag["person"]] if t)]
    if eintrag is not None:
        zeilen.append(f"📄 Jetzt {len(neu_eintrag['seiten'])} Seiten.")
    if neu_eintrag["steuer"]["relevant"]:
        zeilen.append(f"🧾 Steuer {neu_eintrag['steuer']['jahr'] or ''}: {neu_eintrag['steuer']['art']}"
                      + (f" ({euro(neu_eintrag['steuer']['betrag'])})" if neu_eintrag["steuer"].get("betrag") else ""))
    if neu_eintrag["einreichen"].get("noetig") and neu_eintrag["einreichen"].get("status") == "offen":
        zeilen.append("🏥 Noch bei der Versicherung einreichen – „Einreichen“ zeigt alle offenen.")
    for f in neu_eintrag["fristen"]:
        zeilen.append(f"⏰ {de_datum(f['datum'])}: {f['was']} – ich erinnere eine Woche vorher.")
    senden(chat, "\n".join(zeilen))


def _weg(pfad):
    try:
        os.remove(pfad)
    except OSError:
        pass


# ---------- Befehle ----------

def suchen(liste, frage, anzahl=40):
    woerter = [w for w in re.findall(r"[a-zäöüß0-9]{3,}", frage.lower())
               if w not in {"akte", "beleg", "belege", "was", "wie", "wer", "wann", "der", "die", "das", "und", "mir", "uns",
                            "unsere", "unser", "schick", "schicke", "bitte", "von", "vom", "für", "bei", "mit", "zum", "zur"}]
    jahre = re.findall(r"\b(20\d\d)\b", frage)
    bewertet = []
    for i, e in enumerate(liste):
        text = " ".join(str(e.get(k, "")) for k in ("titel", "typ", "kategorie", "absender", "person", "datum", "notiz")).lower()
        text += " " + " ".join(e.get("schlagworte") or []).lower()
        inhalt = (e.get("inhalt") or "").lower()
        p = sum(3 for w in woerter if w in text) + sum(1 for w in woerter if w in inhalt)
        if jahre and any(j in (e.get("datum") or "") for j in jahre):
            p += 2
        if e.get("typ") == "Versicherungspolice":
            p += 0.5
        bewertet.append((p, i))
    bewertet.sort(key=lambda x: (-x[0], -x[1]))
    return [i for p, i in bewertet[:anzahl] if p > 0] or [i for p, i in bewertet[:15]]


def frage_beantworten(chat, frage, liste):
    if not liste:
        senden(chat, "📁 Die Akte ist noch leer – schick mir einfach Fotos oder PDFs von Belegen.")
        return
    treffer = suchen(liste, frage)
    verz = "\n".join(f"[{i + 1}] {zeile(i + 1, liste[i])} | {liste[i].get('typ')} | Steuer: {liste[i]['steuer'].get('art') if liste[i].get('steuer', {}).get('relevant') else '-'}"
                     f" | {(liste[i].get('inhalt') or '')[:300]}" for i in treffer)
    inhalt = []
    groesse = 0
    for i in treffer[:3]:
        pfad = os.path.join(ABLAGE, liste[i].get("datei", ""))
        if os.path.exists(pfad) and groesse + os.path.getsize(pfad) < 15_000_000:
            groesse += os.path.getsize(pfad)
            inhalt.append({"type": "text", "text": f"Dokument [{i + 1}]:"})
            inhalt.append(dokument_block(pfad))
    inhalt.append({"type": "text", "text": f"Heute: {date.today().isoformat()}\nVerzeichnis (Auszug):\n{verz}\n\nFrage: {frage}"})
    a = claude(FRAGE, inhalt, max_tokens=2000, effort="medium")
    senden(chat, "📁 " + (a.get("antwort") or "Dazu habe ich nichts gefunden."))
    for nr in (a.get("senden") or [])[:5]:
        try:
            e = liste[int(nr) - 1]
        except (ValueError, IndexError, TypeError):
            continue
        pfad = os.path.join(ABLAGE, e.get("datei", ""))
        if os.path.exists(pfad):
            datei_senden(chat, pfad, zeile(int(nr), e))


def steuer(chat, jahr, liste):
    auswahl = [e for e in liste if e.get("steuer", {}).get("relevant")
               and str(e["steuer"].get("jahr") or (e.get("datum") or "")[:4]) == str(jahr)]
    if not auswahl:
        senden(chat, f"🧾 Für {jahr} habe ich noch keine steuerrelevanten Belege.")
        return
    gruppen = {}
    for e in auswahl:
        gruppen.setdefault(e["steuer"].get("art") or "Sonstiges", []).append(e)
    zeilen = [f"🧾 Steuer {jahr} – {len(auswahl)} Belege"]
    csv = ["Art;Datum;Absender;Titel;Person;Betrag;absetzbar;Datei"]
    for art, es in sorted(gruppen.items()):
        summe = sum(float(x["steuer"].get("betrag") or x.get("betrag") or 0) for x in es)
        zeilen.append(f"\n▪️ {art}: {len(es)} Belege, {euro(summe)}")
        for x in sorted(es, key=lambda x: x.get("datum") or ""):
            zeilen.append(f"   {de_datum(x.get('datum'))} {x.get('absender', '')} {euro(x.get('betrag')) if x.get('betrag') else ''}")
            csv.append(";".join([art, de_datum(x.get("datum")), x.get("absender", ""), x.get("titel", ""), x.get("person", ""),
                                 euro(x.get("betrag")), euro(x["steuer"].get("betrag")), x.get("datei", "")]))
    erst = [e for e in liste if e.get("typ") == "Erstattung/Leistungsabrechnung" and (e.get("datum") or "")[:4] == str(jahr)]
    if gruppen.get("Krankheitskosten") and erst:
        zeilen.append(f"\nℹ️ Erstattungen der Versicherung {jahr}: {len(erst)} Schreiben – bei Krankheitskosten nur der "
                      f"selbst getragene Teil zählt.")
    zeilen.append("\nAlles ohne Gewähr – bitte mit dem Steuerprogramm/Steuerberater prüfen.")
    senden(chat, "\n".join(zeilen))
    os.makedirs(EXPORT, exist_ok=True)
    zip_pfad = os.path.join(EXPORT, f"Steuer_{jahr}_Belege.zip")
    with zipfile.ZipFile(zip_pfad, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Uebersicht.csv", "﻿" + "\n".join(csv))
        for e in auswahl:
            pfad = os.path.join(ABLAGE, e.get("datei", ""))
            if os.path.exists(pfad):
                z.write(pfad, os.path.join(sicherer_name(e["steuer"].get("art"), 30), os.path.basename(pfad)))
    datei_senden(chat, zip_pfad, f"Steuer {jahr}: alle Belege + Übersicht (öffnet sich in Excel)")


def einreichen(chat, liste):
    offen = [(i, e) for i, e in enumerate(liste) if e.get("einreichen", {}).get("noetig") and e["einreichen"].get("status") == "offen"]
    if not offen:
        senden(chat, "🏥 Keine offenen Arztrechnungen – alles eingereicht. 👍")
        return
    zustand = json_laden(ZUSTAND, {})
    zustand[str(chat)] = [e["id"] for _, e in offen]
    json_schreiben(ZUSTAND, zustand)
    summe = sum(float(e.get("betrag") or 0) for _, e in offen)
    zeilen = [f"🏥 {len(offen)} Belege noch einreichen, zusammen {euro(summe)}:"]
    zeilen += [zeile(n, e) for n, (_, e) in enumerate(offen, 1)]
    zeilen.append("\nDie Dateien kommen gleich. Danach „Eingereicht“ schreiben (oder „Eingereicht 1 3“ für einzelne).")
    senden(chat, "\n".join(zeilen))
    for n, (_, e) in enumerate(offen, 1):
        pfad = os.path.join(ABLAGE, e.get("datei", ""))
        if os.path.exists(pfad):
            datei_senden(chat, pfad, zeile(n, e))


def eingereicht(chat, text, liste):
    ids = json_laden(ZUSTAND, {}).get(str(chat)) or [e["id"] for e in liste if e.get("einreichen", {}).get("status") == "offen"]
    nummern = [int(x) for x in re.findall(r"\b(\d{1,3})\b", text)]
    gewaehlt = [ids[n - 1] for n in nummern if 0 < n <= len(ids)] if nummern else ids
    heute = date.today().isoformat()
    anzahl = 0
    for e in liste:
        if e["id"] in gewaehlt and e.get("einreichen", {}).get("status") == "offen":
            e["einreichen"].update({"status": "eingereicht", "am": heute})
            anzahl += 1
    json_schreiben(VERZEICHNIS, liste)
    senden(chat, f"✅ {anzahl} Beleg(e) als eingereicht markiert." if anzahl else "ℹ️ Nichts zu markieren – „Einreichen“ zeigt die offenen.")


def fristen_text(liste, tage=60):
    heute = date.today()
    bald = []
    for e in liste:
        for f in e.get("fristen") or []:
            try:
                d = datetime.strptime(f["datum"], "%Y-%m-%d").date()
            except (KeyError, ValueError, TypeError):
                continue
            if heute <= d <= heute + timedelta(days=tage):
                bald.append((d, f.get("was", ""), e))
    bald.sort(key=lambda x: x[0])
    return bald


def befehl(auftrag):
    chat = auftrag.get("chat")
    text = (auftrag.get("text") or "").strip()
    liste = verzeichnis()
    t = text.lower().lstrip("/")
    if re.match(r"^(akte|belege?)\s*(hilfe|\?)?\s*$", t):
        senden(chat, HILFE + f"\n\nIn der Akte: {len(liste)} Dokumente.")
    elif re.match(r"^steuer", t):
        j = re.search(r"(20\d\d)", t)
        steuer(chat, int(j.group(1)) if j else date.today().year - (1 if date.today().month < 6 else 0), liste)
    elif re.match(r"^einreichen", t):
        einreichen(chat, liste)
    elif re.match(r"^eingereicht", t):
        eingereicht(chat, t, liste)
    elif re.match(r"^fristen", t):
        bald = fristen_text(liste)
        senden(chat, "⏰ Fristen in den nächsten 8 Wochen:\n" + "\n".join(
            f"{de_datum(d.isoformat())}: {was} ({e.get('titel')}, {e.get('absender')})" for d, was, e in bald)
            if bald else "⏰ In den nächsten 8 Wochen steht nichts an.")
    else:
        frage_beantworten(chat, re.sub(r"^(akte|belege?)\s*[:,-]?\s*", "", text, flags=re.I) or text, liste)


def erinnerung(auftrag):
    chats = [c for c in auftrag.get("chats") or [] if str(c).lstrip("-").isdigit()]
    liste = verzeichnis()
    if auftrag.get("art") == "einreichen":
        offen = [e for e in liste if e.get("einreichen", {}).get("noetig") and e["einreichen"].get("status") == "offen"]
        if offen:
            for c in chats:
                senden(c, f"🏥 Erinnerung: {len(offen)} Arztrechnung(en) über {euro(sum(float(e.get('betrag') or 0) for e in offen))} "
                          f"sind noch nicht eingereicht. „Einreichen“ schickt sie dir.")
        return
    heute = date.today()
    geaendert = False
    for e in liste:
        for f in e.get("fristen") or []:
            try:
                d = datetime.strptime(f["datum"], "%Y-%m-%d").date()
            except (KeyError, ValueError, TypeError):
                continue
            if not f.get("erinnert") and heute <= d <= heute + timedelta(days=7):
                for c in chats:
                    senden(c, f"⏰ In {(d - heute).days} Tag(en), am {d.strftime('%d.%m.%Y')}: {f.get('was')} – "
                              f"{e.get('titel')} ({e.get('absender')})")
                f["erinnert"] = True
                geaendert = True
    if geaendert:
        json_schreiben(VERZEICHNIS, liste)


ANKUENDIGUNG = """Hallo! 👋 Neu im Zuhause-Bot: die digitale Akte 📁

Alle Belege, Rechnungen, Arztrechnungen, Versicherungs- und Behördenbriefe einfach als Foto oder PDF hier an den Bot schicken. Er macht aus Fotos ein PDF, liest den Beleg und sortiert ihn ein: Art, von wem, Datum, Betrag, für wen, Steuer, Fristen.

📸 Ablegen: Foto oder PDF schicken – am sichersten mit dem Text „Beleg“ dazu. Mehrere Seiten: die nächste Seite mit dem Text „+“ hinterherschicken.
🔎 Suchen und fragen: „Akte Was zahlt die Zahnzusatzversicherung bei Implantaten?“ oder „Akte schick mir die Rechnung vom Elektriker“.
🏥 Arztrechnungen: werden als „noch einreichen“ gemerkt. „Einreichen“ schickt dir alle offenen als Dateien (zum Hochladen in die Versicherungs-App), danach „Eingereicht“ schreiben.
🧾 Steuer: „Steuer 2026“ – Übersicht mit Summen und alle Belege als ZIP.
⏰ Fristen: „Fristen“ zeigt, was ansteht. Erinnerungen kommen automatisch eine Woche vorher, offene Arztrechnungen am Monatsanfang.
🖥 Am Monitor im Flur gibt es den Reiter „Akte“ mit Liste, Filtern und Ansicht der PDFs.

Alles bleibt bei uns zu Hause auf dem Home-Assistant-Rechner. „Akte Hilfe“ zeigt diese Übersicht jederzeit wieder."""


# ---------- Monitor-Seite (www/akte.html, schnell und ohne Claude) ----------

ANSICHT = "/media/akte/_ansicht/"   # kurzzeitige Kopie zum Anzeigen (nur mit Home-Assistant-Anmeldung abrufbar)


def seite(auftrag):
    was = auftrag.get("was")
    liste = verzeichnis()
    eintrag = next((e for e in liste if e.get("id") == auftrag.get("id")), None)
    if was == "ansehen" and eintrag:
        import shutil
        os.makedirs(ANSICHT, exist_ok=True)
        for alt in os.listdir(ANSICHT):
            if time.time() - os.path.getmtime(os.path.join(ANSICHT, alt)) > 3600:
                _weg(os.path.join(ANSICHT, alt))
        name = uuid.uuid4().hex + ".pdf"
        shutil.copyfile(os.path.join(ABLAGE, eintrag.get("datei", "")), os.path.join(ANSICHT, name))
        return {"ok": True, "datei": "akte/_ansicht/" + name}
    if was in ("eingereicht", "offen") and eintrag and eintrag.get("einreichen", {}).get("noetig"):
        eintrag["einreichen"].update({"status": was, "am": date.today().isoformat() if was == "eingereicht" else ""})
        json_schreiben(VERZEICHNIS, liste)
    elif was == "loeschen" and eintrag:
        _weg(os.path.join(ABLAGE, eintrag.get("datei", "")))
        for s in eintrag.get("seiten") or []:
            _weg(os.path.join(SEITEN, s))
        liste.remove(eintrag)
        json_schreiben(VERZEICHNIS, liste)
    felder = ("id", "titel", "typ", "kategorie", "absender", "datum", "betrag", "person", "steuer", "einreichen", "fristen",
              "schlagworte", "von", "eingang", "notiz")
    aus = [dict({k: e.get(k) for k in felder}, kurz=(e.get("inhalt") or "")[:500]) for e in liste]
    aus.sort(key=lambda e: (e.get("datum") or "", e.get("eingang") or ""), reverse=True)
    return {"ok": True, "eintraege": aus}


def ankuendigen(auftrag):
    """Einmalig nach dem Update: allen Bot-Nutzern erklären, was neu ist (Merker verhindert Wiederholung)."""
    marke = "/config/.akte_ankuendigung_1"
    if os.path.exists(marke):
        return
    open(marke, "w").close()
    for c in [c for c in auftrag.get("chats") or [] if str(c).lstrip("-").isdigit()]:
        senden(c, ANKUENDIGUNG)


# ---------- Start (lange Arbeit im Hintergrund) ----------

def im_hintergrund(funktion, auftrag):
    if os.fork() > 0:
        return
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    fd = os.open(os.devnull, os.O_RDWR)
    for s in (0, 1, 2):
        os.dup2(fd, s)
    try:
        funktion(auftrag)
    except Exception as fehler:  # noqa: BLE001
        try:
            for c in ([auftrag.get("chat")] if auftrag.get("chat") else auftrag.get("chats") or [])[:1]:
                senden(c, f"⚠️ Akte: Das hat nicht geklappt ({type(fehler).__name__}: {str(fehler)[:200]}). Bitte nochmal versuchen.")
        except Exception:  # noqa: BLE001
            pass
    os._exit(0)


def umziehen():
    """Einmalig: Belege aus der früheren Ablage /media/akte/ in den Konfigurationsordner holen."""
    import shutil
    try:
        namen = os.listdir(ALT)
    except OSError:
        return
    for n in namen:
        quelle = os.path.join(ALT, n)
        if n == "_seiten" or re.match(r"^\d{4}$", n):
            ziel = os.path.join(ABLAGE, n)
            os.makedirs(ziel, exist_ok=True)
            for d in os.listdir(quelle):
                if not os.path.exists(os.path.join(ziel, d)):
                    shutil.move(os.path.join(quelle, d), os.path.join(ziel, d))
            try:
                os.rmdir(quelle)
            except OSError:
                pass


def main():
    aktion = sys.argv[1] if len(sys.argv) > 1 else ""
    auftrag = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8")) if len(sys.argv) > 2 else {}
    for d in (ABLAGE, EINGANG, SEITEN):
        os.makedirs(d, exist_ok=True)
    umziehen()
    if aktion == "seite":
        print(json.dumps(seite(auftrag), ensure_ascii=False))
        return
    funktion = {"neu": ablegen, "befehl": befehl, "erinnerung": erinnerung, "ankuendigen": ankuendigen}.get(aktion)
    if not funktion:
        print(json.dumps({"ok": False, "fehler": "unbekannte Aktion"}))
        return
    im_hintergrund(funktion, auftrag)
    time.sleep(0.2)
    print(json.dumps({"ok": True}))


if __name__ == "__main__":
    main()
