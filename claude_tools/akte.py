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
LOGBUCH = "/config/akte_log.json"       # letzte Aktivitäten (für die Monitor-Seite)
WAPPEN = "/config/akte_wappen.jpg"          # Familienwappen für den Briefkopf (nur lokal)
EINSTELLUNGEN = "/config/akte_einstellungen.json"   # Ordner und Hinweise der Familie (nur lokal, über die Akte-Seite)
SPERRE = "/config/.akte.lock"           # immer nur eine Arbeit gleichzeitig (sonst überschreiben sich Einträge)
STANDARD_ORDNER = []   # Ordner entstehen erst mit den Belegen (Claude schlägt sie vor, die Familie kann umbenennen)

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
 "rechnungsnummer": "Rechnungs-/Vorgangs-/Vertragsnummer oder leer",
 "zahlung": "offen" (Rechnung/Mahnung mit Zahlungsaufforderung), "bezahlt" (Quittung, Kassenbon, Vermerk "bezahlt",
            Abbuchung per Lastschrift angekündigt, Kontoauszug) oder "keine" (kein Zahlungsbeleg),
 "mahnung": true bei Mahnung/Zahlungserinnerung, sonst false,
 "bezug": "bei Mahnung, Erstattung, Gutschrift oder Storno: Nummer der ursprünglichen Rechnung, sonst leer",
 "ordner": "Ordnerpfad „Hauptordner / Unterordner“. Hauptordner = Person (Marco, Mirka, Mathilda, Familie) oder Objekt
            (z. B. „Nadorster Str. 299“, „Hof Fünfhauser Weg 7“, „Auto“). Unterordner = Thema (z. B. „Versicherungen“, „Rente“,
            „Gesundheit“, „Bank & Verträge“, „Steuer“, „Oberwohnung“, „Ferienwohnung“, „Haus allgemein“). Persönliche Dokumente
            (an eine Person gerichtet: Versicherung, Rente, Arzt, Gehalt) gehören zur Person, Dokumente zu Gebäude/Wohnung zum Objekt.
            Vorhandene Ordner bevorzugen (siehe unten), sonst passend neu anlegen; bei echter Unsicherheit leer lassen und nachfragen",
 "fortsetzung": true, wenn dieses Bild nur eine weitere Seite des unten genannten vorherigen Dokuments ist (gleicher Absender,
                "Seite 2 von …", kein eigener Briefkopf/Betreff), sonst false,
 "frage": "nur wenn du dir bei Ordner, Person, Zweck oder Steuer NICHT sicher bist: eine kurze Rückfrage an die Familie
           (z. B. „Für welche Wohnung war diese Handwerkerrechnung?“), sonst leer",
 "vorschlaege": ["2–4 kurze Antwortmöglichkeiten zur Frage, möglichst Ordnernamen"] oder [],
 "einreichen": true, wenn es eine Rechnung über Behandlung/Arznei/Hilfsmittel/Zahnarzt/Heilpraktiker ist, die man bei einer
               privaten Krankenversicherung, Beihilfe oder Zusatzversicherung zur Erstattung einreicht, sonst false,
 "fristen": [{{"datum": "JJJJ-MM-TT", "was": "z. B. Zahlung fällig / Einspruchsfrist / Kündigungsfrist / Garantie endet"}}],
 "schlagworte": ["5–10 Suchwörter, auch Synonyme"],
 "inhalt": "bei kurzen Dokumenten der vollständige wichtige Text; bei langen (Policen, Verträgen) alle wichtigen Fakten:
            Vertrags-/Versicherungsnummer, Tarif, Leistungen mit Prozent/Höchstbeträgen, Selbstbehalt, Beitrag, Laufzeit,
            Kündigung – höchstens 600 Wörter",
 "antwort": "1–2 kurze Sätze für den Chat, was abgelegt wurde (ohne Nummern und Codes)"}}
Vermietung: Betrifft eine Rechnung ein vermietetes Objekt (Mietobjekt, Mieter/in genannt, Ferienwohnung, Stellplätze), dann
kategorie "Vermietung" und steuer.art "Vermietung" mit dem vollen Betrag (Werbungskosten). "Handwerkerleistung" nur für den
selbst bewohnten Haushalt, dann nur Arbeits-, Fahrt- und Maschinenkosten inkl. MwSt. als steuer.betrag.
Ein Aufmaß, Angebot oder Lieferschein ist keine Rechnung: typ "Sonstiges" bzw. passend, steuer.relevant false.
Frage lieber nach, als falsch einzusortieren – aber nur, wenn es wirklich unklar ist. Steht eine Antwort der Familie in der
Notiz, nicht noch einmal fragen. Steht beim Text dazu eine Notiz der Familie (z. B. "ist schon bezahlt", "gehört zur Ferienwohnung"), gilt sie vorrangig.
Fristen nur, wenn sie wirklich im Dokument stehen oder sich klar ergeben (Einspruch: 1 Monat nach Bescheid-Datum).
Wenn etwas unleserlich ist, lieber leer lassen als raten."""

FRAGE = """Du beantwortest Fragen zur digitalen Akte einer Familie (Belege, Versicherungen, Verträge, Bescheide).
Unten stehen passende Einträge aus dem Verzeichnis, die wichtigsten Dokumente sind angehängt. Antworte auf Deutsch, kurz und
konkret, nenne die Quelle (Titel + Datum). Steht die Antwort nicht drin, sag das ehrlich. Keine Rechts- oder Steuerberatung
erfinden. Antworte NUR mit JSON: {"antwort": "Text für Telegram", "senden": [Nummern der Einträge, die als Datei mitgeschickt
werden sollen – nur wenn danach gefragt wird ("schick mir …") oder es klar hilft, höchstens 5],
 "aenderungen": [nur wenn die Nachricht etwas über einen Eintrag MITTEILT, z. B. "die Rechnung vom Fliesenleger ist bezahlt"
                 oder "das gehört zur Ferienwohnung": {"nr": Nummer, "notiz": "kurze Notiz", "zahlung": "bezahlt"|"offen",
                 "kategorie": "…", "steuer_art": "…", "eingereicht": true}] – nur die Felder, die sich ändern}"""

SCHREIBEN = """Du setzt für eine Familie in Deutschland einen kurzen, höflichen, sachlichen Brief auf (DIN 5008).
Grundlage: der Auftrag der Familie, das angehängte Dokument (falls vorhanden; daraus Empfänger-Anschrift, Kunden-/
Aktenzeichen, Datum des Schreibens) und die Hinweise der Familie (Namen, Anschrift, Telefonnummern, E-Mail). Erfinde nichts:
Fehlt etwas Wichtiges (z. B. die neue Adresse), schreibe "[bitte ergänzen: …]" an die Stelle.
Absender ist die Person, an die das Dokument gerichtet ist bzw. um die es geht (z. B. Mirka bei Mirkas Versicherung),
mit IHREM Namen, IHRER Telefonnummer und ggf. E-Mail aus den Hinweisen; sonst Marco. Der Betreff nennt immer die
Vertrags-, Versicherungs-, Kunden- oder Aktennummer aus dem Dokument. Antworte NUR mit JSON:
{"absender": ["Vorname Nachname", "Straße Nr", "PLZ Ort"], "empfaenger": ["Firma/Behörde", "ggf. Abteilung", "Straße", "PLZ Ort"],
 "info": [{"bezeichnung": "Vertragsnummer" / "Versicherungsnummer" / "Kundennummer" / "Ihr Zeichen", "wert": "…"},
          {"bezeichnung": "Ihr Schreiben vom", "wert": "TT.MM.JJJJ"}, {"bezeichnung": "Telefon", "wert": "Nummer des Absenders"}],
 "fuss": ["Name · Straße Nr · PLZ Ort", "Telefon … · E-Mail … (nur was in den Hinweisen steht)"],
 "email": "E-Mail-Adresse des Empfängers: zuerst aus dem Dokument; sonst nur eine offiziell bekannte allgemeine
           Kontaktadresse dieser Stelle, wenn du dir sehr sicher bist; sonst leer",
 "email_quelle": "Dokument" oder "allgemein bekannt – bitte prüfen" oder "",
 "mailtext": "kurzer Begleittext für die Mail (2–3 Sätze, mit Anrede und Gruß), das PDF hängt an",
 "ort": "Ort des Absenders", "betreff": "Betreff mit Kunden-/Aktenzeichen",
 "text": "Anrede und Brieftext – OHNE Grußformel und OHNE Namen am Ende (die setzt das Layout selbst)",
 "name": "Name für die Unterschrift", "dateiname": "kurzer Dateiname ohne Endung"}"""

DURCHSICHT = """Du gehst die digitale Akte einer Familie durch (Liste unten, je Eintrag mit Nummer). Prüfe:
- Mahnungen: gibt es die ursprüngliche Rechnung? Ist sie laut Notiz/Status bezahlt? Dann die Mahnung als bezahlt markieren.
- Doppelte Einträge (gleicher Absender, Datum, Betrag), Aufmaße/Angebote ohne zugehörige Rechnung.
- Kategorie und Steuer-Zuordnung offensichtlich falsch? (Rechnungen für vermietete Objekte → Vermietung)
- Offene Zahlungen, deren Fälligkeit vorbei ist.
- Einzelne Seiten EINES Schreibens, die als getrennte Einträge abgelegt wurden (gleicher Absender/Datum, "Seite 2", Fortsetzung)
  → in "zusammenfuehren" als Gruppe von Nummern in Seitenreihenfolge (nur Einträge mit "Fotos").
- Liegt jeder Eintrag im richtigen Ordner der Familie?
Antworte NUR mit JSON: {"aenderungen": [{"nr": Nummer, "notiz": "…", "zahlung": "bezahlt"|"offen", "kategorie": "…",
"steuer_art": "…", "ordner": "…"} – nur sichere Korrekturen, nur geänderte Felder], "zusammenfuehren": [[Nummern], …], "bericht": "kurzer Überblick für Telegram (max. 10 Zeilen):
was auffällt und was zu tun ist; leer lassen, wenn nichts Wichtiges"}"""

HILFE = """📁 Digitale Akte – so geht's
• Ohne Telegram: in Home Assistant unter Medien → Lokale Medien → Ordner „Akte-Eingang“ Dateien hochladen.
• Beleg ablegen: Foto oder PDF an den Bot schicken. Rechnungen, Arztrechnungen, Versicherungsbriefe usw. erkennt er selbst;
  sicherheitshalber „Beleg“ als Text zum Foto schreiben.
• Mehrseitig: weitere Seiten mit dem Text „+“ hinterherschicken (innerhalb einer Stunde).
• Suchen/fragen: „Akte Was zahlt die Zahnzusatz bei Implantaten?“, „Akte schick mir die Rechnung vom Elektriker“
• Steuer: „Steuer 2026“ – Übersicht mit Summen + ZIP mit allen Belegen
• Arztrechnungen: „Einreichen“ – offene Belege als Dateien; danach „Eingereicht“ (alle) oder „Eingereicht 1 3“
• Fristen: „Fristen“ – was in den nächsten Wochen fällig ist
• Wappen für den Briefkopf: Bild mit dem Text „Wappen“ schicken
• Schreiben: „Schreiben an die Agentur für Arbeit: bitte Adresse ändern auf …“ – ich setze den Brief als PDF auf
  (sucht sich das passende Dokument aus der Akte, z. B. für Kundennummer und Anschrift)
• Infos dazu: „Akte Die Rechnung vom Fliesenleger ist bezahlt“ oder „Akte Heizungsrechnung gehört zur Ferienwohnung“ –
  wird beim Beleg vermerkt. Kommt eine Mahnung, sage ich, ob sie laut Akte schon bezahlt ist.
• Jeden Sonntag gehe ich die Akte durch und melde, was auffällt (Mahnungen, offene Zahlungen, fehlende Rechnungen).
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


def einstellungen():
    d = json_laden(EINSTELLUNGEN, {})
    ordner = [o for o in (d.get("ordner") or []) if isinstance(o, dict) and o.get("name")] or STANDARD_ORDNER
    return {"ordner": ordner, "hinweise": d.get("hinweise") or ""}


def alle_ordner():
    """Ordner aus den Einstellungen plus alle, die schon in der Akte benutzt werden."""
    namen = [o["name"] for o in einstellungen()["ordner"]]
    for e in verzeichnis():
        if e.get("ordner") and e["ordner"] not in namen:
            namen.append(e["ordner"])
    return namen


def familien_kontext():
    """Ordner und Hinweise der Familie als Text für Claude (stehen nur lokal, nicht im Programm)."""
    e = einstellungen()
    beschr = {o["name"]: o.get("beschreibung", "") for o in e["ordner"]}
    namen = alle_ordner()
    t = "Vorhandene Ordner:\n" + ("\n".join(f"- {n}" + (f": {beschr[n]}" if beschr.get(n) else "") for n in namen)
                                   if namen else "(noch keine – lege passende neu an)")
    if e["hinweise"]:
        t += "\nHinweise der Familie:\n" + e["hinweise"]
    return t


def ordner_name(name):
    """Vorhandenen Ordner finden (Groß-/Kleinschreibung egal) oder einen neuen übernehmen; leer = noch unsortiert.
    Unterordner mit " / " getrennt (z. B. "Mirka / Versicherungen")."""
    teile = [re.sub(r"\s+", " ", t).strip() for t in re.split(r"\s*/\s*|\s+»\s+|\s+>\s+", str(name or ""))]
    name = " / ".join(t for t in teile if t)[:100]
    if not name:
        return ""
    return {n.lower(): n for n in alle_ordner()}.get(name.lower(), name)


class Sperre:
    def __init__(self, warten=None):
        self.warten = warten

    def __enter__(self):
        import fcntl
        self.f = open(SPERRE, "w")
        if self.warten is None:
            fcntl.flock(self.f, fcntl.LOCK_EX)
            return self
        ende = time.time() + self.warten
        while True:
            try:
                fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.time() > ende:
                    raise RuntimeError("Akte ist gerade beschäftigt – gleich nochmal versuchen")
                time.sleep(0.5)

    def __exit__(self, *a):
        import fcntl
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def logbuch(text, art="ok"):
    log = json_laden(LOGBUCH, [])
    log = (log if isinstance(log, list) else [])[-49:] + [{"zeit": datetime.now().strftime("%d.%m. %H:%M"), "text": text[:200], "art": art}]
    try:
        json_schreiben(LOGBUCH, log)
    except OSError:
        pass


def senden(chat, text):
    if not chat:
        return
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

def wappen_speichern(quelle_oder_bytes):
    """Bild als Familienwappen für den Briefkopf ablegen (weißer Hintergrund statt Transparenz, max. 800 px)."""
    from PIL import Image
    img = Image.open(io.BytesIO(quelle_oder_bytes) if isinstance(quelle_oder_bytes, bytes) else quelle_oder_bytes)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        grund = Image.new("RGB", img.size, "white")
        grund.paste(img, mask=img.split()[-1])
        img = grund
    img = img.convert("RGB")
    img.thumbnail((800, 800))
    img.save(WAPPEN, "JPEG", quality=90)


def ablegen(auftrag):
    chat = auftrag.get("chat")
    quelle = auftrag.get("datei", "")
    if re.match(r"^\s*wappen\b", auftrag.get("text") or "", re.I) and not quelle.lower().endswith(".pdf") and os.path.exists(quelle):
        wappen_speichern(quelle)
        _weg(quelle)
        logbuch("Familienwappen gespeichert")
        senden(chat, "🛡 Danke! Das Wappen steht ab jetzt oben rechts in jedem Schreiben aus der Akte.")
        return
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

    # vorheriger Foto-Beleg aus diesem Chat (letzte 15 Minuten) – vielleicht ist das hier nur seine nächste Seite
    vorher = None
    if eintrag is None and not ist_pdf:
        grenze = (datetime.now() - timedelta(minutes=15)).isoformat()
        vorher = next((x for x in reversed(liste) if str(x.get("chat")) == str(chat) and x.get("seiten")
                       and x.get("eingang", "") >= grenze), None)

    def lesen(bloecke_):
        kontext = familien_kontext()
        if vorher is not None and eintrag is None:
            kontext += (f"\nVorheriges Dokument in diesem Chat (vor wenigen Minuten): {vorher.get('titel')} von "
                        f"{vorher.get('absender')}, {vorher.get('datum')}, {len(vorher.get('seiten') or [])} Seite(n).")
        return claude(LESEN, bloecke_ + [{"type": "text", "text": f"Heute: {date.today().isoformat()}\nVon: {auftrag.get('von', '')}\n"
                                                                    f"Text dazu: {text or '(keiner)'}\n{kontext}"}], max_tokens=4000)

    # Claude liest das Dokument (alle Seiten)
    if ist_pdf:
        e = lesen([dokument_block(quelle)])
    else:
        e = lesen([dokument_block(s) for s in seiten])
        if vorher is not None and e.get("fortsetzung"):
            # doch nur die nächste Seite: an den vorherigen Beleg hängen und alles zusammen neu lesen
            eintrag = vorher
            eintrag["seiten"].append(os.path.basename(seite))
            seiten = [os.path.join(SEITEN, s_) for s_ in eintrag["seiten"]]
            vorher = None
            e = lesen([dokument_block(s_) for s_ in seiten])

    jahr = (e.get("datum") or "")[:4] if re.match(r"^\d{4}-\d\d-\d\d$", e.get("datum") or "") else str(date.today().year)
    unterordner = os.path.join(ordner_pfad(ordner_name(e.get("ordner"))), jahr)
    os.makedirs(os.path.join(ABLAGE, unterordner), exist_ok=True)
    name = "_".join([e.get("datum") or date.today().isoformat(), sicherer_name(e.get("typ"), 25), sicherer_name(e.get("absender"))])
    if e.get("betrag"):
        name += "_" + sicherer_name(f"{float(e['betrag']):.2f}".replace(".", "-"), 12)
    if eintrag is not None and eintrag.get("datei"):
        _weg(os.path.join(ABLAGE, eintrag["datei"]))
    ziel_rel = os.path.join(unterordner, name + ".pdf")
    n = 2
    while os.path.exists(os.path.join(ABLAGE, ziel_rel)) and (eintrag is None or eintrag.get("datei") != ziel_rel):
        ziel_rel = os.path.join(unterordner, f"{name}_{n}.pdf")
        n += 1
    ziel = os.path.join(ABLAGE, ziel_rel)
    if ist_pdf:
        import shutil
        shutil.move(quelle, ziel)   # Eingang (/media) und Ablage (/config) liegen auf verschiedenen Laufwerken
    else:
        seiten_zu_pdf(seiten, ziel)
        _weg(quelle)

    neu_eintrag = eintrag or {"id": datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4], "sha": pruef,
                              "eingang": datetime.now().isoformat(timespec="seconds"), "chat": chat,
                              "von": auftrag.get("von", ""), "seiten": [] if ist_pdf else [os.path.basename(seite)]}
    felder_setzen(neu_eintrag, e, jahr)
    neu_eintrag["datei"] = ziel_rel
    if text and not re.match(r"^\s*(\+|beleg|akte|weiter|seite\s*\d*|rückseite|rueckseite)\s*$", text, re.I):
        neu_eintrag["notiz"] = text
    if eintrag is None:
        liste.append(neu_eintrag)
    hinweis_mahnung = mahnung_pruefen(liste, neu_eintrag)
    json_schreiben(VERZEICHNIS, liste)
    logbuch(f"Abgelegt: {neu_eintrag['titel']} ({neu_eintrag['absender']})")

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
        if f["datum"] >= date.today().isoformat():
            zeilen.append(f"⏰ {de_datum(f['datum'])}: {f['was']} – ich erinnere eine Woche vorher.")
    if hinweis_mahnung:
        zeilen.append(hinweis_mahnung)
    if neu_eintrag.get("notiz"):
        zeilen.append(f"📝 Notiz: {neu_eintrag['notiz']}")
    if neu_eintrag.get("frage"):
        zeilen.append(f"❓ Rückfrage: {neu_eintrag['frage']}"
                      + (f" ({' / '.join(neu_eintrag['vorschlaege'])})" if neu_eintrag.get("vorschlaege") else "")
                      + "\nAntwort im Reiter Akte (gelbe Blase) oder hier: „Akte …“ mit der Antwort.")
    senden(chat, "\n".join(zeilen))


def felder_setzen(eintrag, e, jahr=None):
    """Ergebnis von Claude ins Verzeichnis übernehmen (Status wie "eingereicht" und Notizen bleiben erhalten)."""
    jahr = jahr or (e.get("datum") or "")[:4]
    steuer = e.get("steuer") if isinstance(e.get("steuer"), dict) else {}
    alt_einreichen = eintrag.get("einreichen") or {}
    eintrag.update({
        "typ": e.get("typ") or "Sonstiges", "kategorie": e.get("kategorie") or "Sonstiges",
        "titel": e.get("titel") or e.get("typ") or "Dokument", "absender": e.get("absender") or "",
        "datum": e.get("datum") or "", "betrag": e.get("betrag"), "person": e.get("person") or "",
        "ordner": eintrag.get("ordner") if eintrag.get("ordner_fest") else ordner_name(e.get("ordner")),
        "rechnungsnummer": e.get("rechnungsnummer") or "", "bezug": e.get("bezug") or "",
        "mahnung": bool(e.get("mahnung")),
        "zahlung": eintrag.get("zahlung") if eintrag.get("zahlung_fest") else (e.get("zahlung") or "keine"),
        "steuer": {"relevant": bool(steuer.get("relevant")), "art": steuer.get("art") or "keine",
                   "jahr": steuer.get("jahr") or (int(jahr) if str(jahr).isdigit() else None), "betrag": steuer.get("betrag")},
        "einreichen": {"noetig": True, "status": alt_einreichen.get("status", "offen"), "am": alt_einreichen.get("am", "")}
                      if e.get("einreichen") else {"noetig": False},
        "fristen": [{"datum": f.get("datum"), "was": f.get("was", ""), "erinnert": False}
                    for f in (e.get("fristen") or []) if re.match(r"^\d{4}-\d\d-\d\d$", str(f.get("datum", "")))],
        "schlagworte": e.get("schlagworte") or [], "inhalt": (e.get("inhalt") or "")[:6000],
        "frage": "" if eintrag.get("beantwortet") else str(e.get("frage") or "")[:300],
        "vorschlaege": [] if eintrag.get("beantwortet") else [str(v)[:60] for v in (e.get("vorschlaege") or [])[:4]],
    })


def ordner_pfad(ordner):
    """Ordnerpfad → Unterverzeichnisse auf der Platte (jede Ebene für sich)."""
    return os.path.join(*[sicherer_name(t, 50) for t in (ordner or "Unsortiert").split(" / ") if t.strip()] or ["Unsortiert"])


def datei_einordnen(e):
    """PDF in den Ordner/Jahr-Unterordner legen, der zum Eintrag passt (nach Änderungen)."""
    alt = e.get("datei") or ""
    jahr = (e.get("datum") or "")[:4] if re.match(r"^\d{4}", e.get("datum") or "") else alt.split("/")[-2] if "/" in alt else str(date.today().year)
    soll = os.path.join(ordner_pfad(e.get("ordner")), jahr)
    if os.path.dirname(alt) == soll or not os.path.exists(os.path.join(ABLAGE, alt)):
        return
    os.makedirs(os.path.join(ABLAGE, soll), exist_ok=True)
    neu = os.path.join(soll, os.path.basename(alt))
    if os.path.exists(os.path.join(ABLAGE, neu)):
        neu = os.path.join(soll, uuid.uuid4().hex[:4] + "_" + os.path.basename(alt))
    os.replace(os.path.join(ABLAGE, alt), os.path.join(ABLAGE, neu))
    e["datei"] = neu


def zusammenfuehren(liste, gruppe):
    """Mehrere Foto-Belege (einzelne Seiten) zu einem zusammenführen und neu lesen."""
    es = [e for e in gruppe if e in liste and e.get("seiten")]
    if len(es) < 2:
        return None
    haupt = es[0]
    for e in es[1:]:
        haupt["seiten"] += e["seiten"]
        _weg(os.path.join(ABLAGE, e.get("datei", "")))
        if e.get("notiz"):
            haupt["notiz"] = ((haupt.get("notiz") or "") + " · " + e["notiz"]).strip(" ·")
        liste.remove(e)
    pfad = os.path.join(ABLAGE, haupt.get("datei", ""))
    seiten_zu_pdf([os.path.join(SEITEN, s) for s in haupt["seiten"]], pfad)
    bloecke = [dokument_block(os.path.join(SEITEN, s)) for s in haupt["seiten"]]
    bloecke.append({"type": "text", "text": f"Heute: {date.today().isoformat()}\nNotiz der Familie: {haupt.get('notiz') or '(keine)'}\n{familien_kontext()}"})
    felder_setzen(haupt, claude(LESEN, bloecke, max_tokens=4000))
    datei_einordnen(haupt)
    return haupt


def aenderungen_anwenden(liste, aenderungen, nummern=None):
    """Änderungen aus Fragen/Durchsicht (Nummern 1-basiert, ggf. über eine Auswahl) übernehmen."""
    texte = []
    for a in aenderungen or []:
        try:
            i = int(a.get("nr")) - 1
            e = liste[nummern[i]] if nummern is not None else liste[i]
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
        if a.get("notiz"):
            e["notiz"] = (((e.get("notiz") or "") + " · ") if e.get("notiz") else "") + str(a["notiz"])[:300]
            if e.get("frage"):
                e.update({"frage": "", "vorschlaege": [], "beantwortet": True})
        if a.get("zahlung") in ("bezahlt", "offen"):
            e["zahlung"], e["zahlung_fest"] = a["zahlung"], True
        if a.get("kategorie"):
            e["kategorie"] = str(a["kategorie"])[:40]
        if a.get("ordner"):
            e["ordner"], e["ordner_fest"] = ordner_name(a["ordner"]), True
            datei_einordnen(e)
        if a.get("steuer_art") and a["steuer_art"] in STEUER_ARTEN:
            e.setdefault("steuer", {}).update({"art": a["steuer_art"], "relevant": a["steuer_art"] != "keine"})
        if a.get("eingereicht") and e.get("einreichen", {}).get("noetig"):
            e["einreichen"].update({"status": "eingereicht", "am": date.today().isoformat()})
        texte.append(f"{e.get('titel')} ({e.get('absender')})")
    return texte


def mahnung_pruefen(liste, neu):
    """Bei einer Mahnung die ursprüngliche Rechnung suchen und sagen, ob sie laut Akte schon bezahlt ist."""
    if not neu.get("mahnung"):
        return ""
    nr = (neu.get("bezug") or neu.get("rechnungsnummer") or "").strip()
    kandidaten = [e for e in liste if e is not neu and not e.get("mahnung") and (
        (nr and nr in (e.get("rechnungsnummer") or "")) or
        (e.get("absender") and e.get("absender") == neu.get("absender") and e.get("betrag") and e.get("betrag") == neu.get("betrag")))]
    if not kandidaten:
        return "⚠️ Mahnung – die ursprüngliche Rechnung habe ich nicht in der Akte."
    r = kandidaten[-1]
    if r.get("zahlung") == "bezahlt":
        neu["notiz"] = ((neu.get("notiz") or "") + " · laut Akte bezahlt").strip(" ·")
        return f"✅ Mahnung zu „{r.get('titel')}“ vom {de_datum(r.get('datum'))} – laut Akte schon bezahlt" + \
               (f" (Notiz: {r.get('notiz')})" if r.get("notiz") else "") + ". Ggf. beim Absender melden."
    return f"⚠️ Mahnung zu „{r.get('titel')}“ vom {de_datum(r.get('datum'))} – laut Akte noch nicht bezahlt. " \
           f"Wenn doch bezahlt: „Akte {r.get('absender')} ist bezahlt“ schreiben."


def neu_lesen(auftrag):
    """Einen Eintrag mit Notiz neu einordnen lassen (z. B. nach "gehört zur Ferienwohnung")."""
    liste = verzeichnis()
    e = next((x for x in liste if x.get("id") == auftrag.get("id")), None)
    if not e:
        return
    pfad = os.path.join(ABLAGE, e.get("datei", ""))
    bloecke = [dokument_block(pfad), {"type": "text", "text": f"Heute: {date.today().isoformat()}\nNotiz der Familie: {e.get('notiz') or '(keine)'}\n{familien_kontext()}"}]
    felder_setzen(e, claude(LESEN, bloecke, max_tokens=4000))
    datei_einordnen(e)
    json_schreiben(VERZEICHNIS, liste)
    logbuch(f"Neu eingeordnet: {e.get('titel')}")


def alle_neu_lesen(auftrag):
    """Alle Belege mit den aktuellen Ordnern/Hinweisen neu einordnen, danach Durchsicht (Seiten zusammenführen usw.)."""
    for e in list(verzeichnis()):
        try:
            neu_lesen({"id": e.get("id")})
        except Exception as fehler:  # noqa: BLE001
            logbuch(f"Fehler bei {e.get('titel')}: {str(fehler)[:120]}", "fehler")
    durchsicht(auftrag)
    logbuch("Alle Belege neu eingeordnet")


def chat_fuer(wer, chats):
    """Telegram-Chat der Person, die auf der Seite angemeldet ist (Vorname im Chat), sonst der erste."""
    chats = [c for c in chats or [] if str(c).lstrip("-").isdigit()]
    if wer:
        for c in chats:
            try:
                if (wer.split()[0].lower() in (telegram("getChat", {"chat_id": c})["result"].get("first_name") or "").lower()):
                    return c
            except Exception:  # noqa: BLE001
                pass
    return chats[0] if chats else None


def teilen(auftrag):
    """PDF eines Eintrags per Telegram schicken – von dort lässt es sich speichern, teilen oder per Mail weiterleiten."""
    e = next((x for x in verzeichnis() if x.get("id") == auftrag.get("id")), None)
    chat = auftrag.get("chat") or chat_fuer(auftrag.get("wer"), auftrag.get("chats"))
    if e and chat:
        datei_senden(chat, os.path.join(ABLAGE, e.get("datei", "")), zeile(1, e)[3:])


def schreiben(auftrag):
    """Brief zu einem Beleg (oder frei) aufsetzen, als PDF ablegen und per Telegram schicken."""
    import brief_pdf
    liste = verzeichnis()
    chat = auftrag.get("chat") or chat_fuer(auftrag.get("wer"), auftrag.get("chats"))
    bezug = next((x for x in liste if x.get("id") == auftrag.get("id")), None)
    if bezug is None and auftrag.get("id") is None and liste:
        treffer = suchen(liste, auftrag.get("text") or "", 1)
        bezug = liste[treffer[0]] if treffer else None
    inhalt = []
    if bezug is not None:
        inhalt.append(dokument_block(os.path.join(ABLAGE, bezug.get("datei", ""))))
    inhalt.append({"type": "text", "text": f"Heute: {date.today().strftime('%d.%m.%Y')}\n{familien_kontext()}\n\n"
                                           f"Auftrag der Familie: {auftrag.get('text') or ''}"})
    b = claude(SCHREIBEN, inhalt, max_tokens=3000, effort="medium")
    if not b.get("text"):
        senden(chat, "⚠️ Das Schreiben konnte ich nicht aufsetzen – bitte den Auftrag etwas genauer beschreiben.")
        return
    ordner = (bezug or {}).get("ordner") or "Schreiben"
    ziel_rel = os.path.join(ordner_pfad(ordner), str(date.today().year),
                            f"{date.today().isoformat()}_Schreiben_{sicherer_name(b.get('dateiname') or b.get('betreff'), 50)}.pdf")
    os.makedirs(os.path.dirname(os.path.join(ABLAGE, ziel_rel)), exist_ok=True)
    info = [(str(i.get("bezeichnung") or ""), str(i.get("wert") or "")) for i in (b.get("info") or []) if isinstance(i, dict)]
    # Grußformel und Name am Ende entfernen, falls Claude sie doch mitgeschrieben hat (das Layout setzt sie selbst)
    b["text"] = re.sub(r"\n\s*(mit freundlichen grüßen|freundliche grüße|viele grüße|beste grüße|mit besten grüßen)[\s\S]*$", "",
                       (b.get("text") or "").rstrip(), flags=re.I).rstrip()
    wappen = open(WAPPEN, "rb").read() if os.path.exists(WAPPEN) else None
    brief_pdf.brief(os.path.join(ABLAGE, ziel_rel), b.get("absender") or [], b.get("empfaenger") or [],
                    f"{b.get('ort') or 'Ovelgönne'}, {date.today().strftime('%d.%m.%Y')}", b.get("betreff") or "", b.get("text") or "",
                    name=b.get("name") or "", info=info[:4], fuss=[str(z) for z in (b.get("fuss") or []) if z][:2] or None, wappen=wappen)
    neu = {"id": datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4], "eingang": datetime.now().isoformat(timespec="seconds"),
           "chat": chat, "von": "Akte (Schreiben)", "datei": ziel_rel, "typ": "Eigenes Schreiben", "kategorie": (bezug or {}).get("kategorie", "Sonstiges"),
           "titel": b.get("betreff") or "Schreiben", "absender": (b.get("empfaenger") or [""])[0], "datum": date.today().isoformat(),
           "betrag": None, "person": b.get("name") or "", "ordner": ordner, "ordner_fest": True, "zahlung": "keine",
           "steuer": {"relevant": False, "art": "keine"}, "einreichen": {"noetig": False}, "fristen": [], "schlagworte": ["Schreiben"],
           "inhalt": b.get("text", "")[:6000], "notiz": f"Aufgesetzt: {auftrag.get('text') or ''}"[:300],
           "bezug_id": (bezug or {}).get("id", ""), "email_empfaenger": b.get("email") or ""}
    liste = verzeichnis()
    liste.append(neu)
    json_schreiben(VERZEICHNIS, liste)
    logbuch(f"Schreiben aufgesetzt: {neu['titel']}")
    if chat:
        datei_senden(chat, os.path.join(ABLAGE, ziel_rel), f"✍️ {neu['titel']}")
        zeilen = ["✍️ Schreiben ist fertig und liegt in der Akte (Ordner „" + ordner + "“). Bitte einmal lesen – "
                  "Stellen mit [bitte ergänzen] noch ausfüllen.",
                  "", "📮 Anschrift:", *[z for z in (b.get("empfaenger") or []) if z]]
        if neu["email_empfaenger"]:
            zeilen += ["", f"✉️ Mail an: {neu['email_empfaenger']}" + (f" ({b.get('email_quelle')})" if b.get("email_quelle") else "")]
        else:
            zeilen += ["", "✉️ Eine Mail-Adresse habe ich im Dokument nicht gefunden – dann per Post oder über das Kontaktformular der Stelle."]
        senden(chat, "\n".join(zeilen))
        # Mailtext extra, damit er sich mit einem Tipp kopieren lässt
        mailtext = b.get("mailtext") or "Sehr geehrte Damen und Herren,\n\nanbei mein Schreiben.\n\nMit freundlichen Grüßen"
        senden(chat, f"Betreff: {neu['titel']}\n\n{mailtext}")


def einmalig_neu(auftrag):
    marke = "/config/.akte_neusortierung_2"
    if os.path.exists(marke) or not verzeichnis():
        return
    open(marke, "w").close()
    for e in verzeichnis():
        if not e.get("ordner_fest"):
            try:
                neu_lesen({"id": e.get("id")})
            except Exception as fehler:  # noqa: BLE001
                logbuch(f"Fehler bei {e.get('titel')}: {str(fehler)[:120]}", "fehler")
    durchsicht(auftrag)
    logbuch("Alle Belege in Ordner und Unterordner einsortiert")


def durchsicht(auftrag):
    """Wöchentlich (und nach dem Hochladen mehrerer Dateien): alles prüfen, Sicheres korrigieren, Auffälliges melden."""
    liste = verzeichnis()
    if not liste:
        return
    zeilen = []
    for n, e in enumerate(liste, 1):
        st = e.get("steuer") or {}
        zeilen.append(" | ".join(str(x) for x in [n, e.get("typ"), e.get("titel"), e.get("absender"), e.get("datum"), e.get("betrag"),
                      "Nr " + (e.get("rechnungsnummer") or "-"), "Bezug " + (e.get("bezug") or "-"), "Zahlung " + (e.get("zahlung") or "?"),
                      "Mahnung" if e.get("mahnung") else "", e.get("kategorie"), "Steuer " + (st.get("art") if st.get("relevant") else "-"),
                      "Fristen " + ", ".join(f"{f.get('datum')} {f.get('was')}" for f in e.get("fristen") or []),
                      "Ordner " + (e.get("ordner") or "-"), f"Fotos {len(e.get('seiten') or [])}" if e.get("seiten") else "PDF",
                      "Notiz " + (e.get("notiz") or "-"), (e.get("inhalt") or "")[:160].replace("\n", " ")]))
    a = claude(DURCHSICHT, [{"type": "text", "text": f"Heute: {date.today().isoformat()}\n{familien_kontext()}\n\n" + "\n".join(zeilen)}],
               max_tokens=3000, effort="medium")
    geaendert = aenderungen_anwenden(liste, a.get("aenderungen"))
    gruppen = []
    for g in a.get("zusammenfuehren") or []:
        try:
            gruppen.append([liste[int(n) - 1] for n in g])
        except (TypeError, ValueError, IndexError):
            continue
    for g in gruppen:
        h = zusammenfuehren(liste, g)
        if h:
            geaendert.append(f"{len(g)} Seiten zusammengeführt: {h.get('titel')}")
    if geaendert:
        json_schreiben(VERZEICHNIS, liste)
    bericht = (a.get("bericht") or "").strip()
    logbuch("Durchsicht: " + (f"{len(geaendert)} Korrektur(en)" if geaendert else "alles in Ordnung"))
    if bericht or geaendert:
        text = "🗂 Akte-Durchsicht\n" + (bericht or "") + (("\n\n✏️ Angepasst: " + "; ".join(geaendert)) if geaendert else "")
        for c in auftrag.get("chats") or ([auftrag["chat"]] if auftrag.get("chat") else []):
            senden(c, text)


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
    verz = "\n".join(f"[{i + 1}] {zeile(i + 1, liste[i])} | {liste[i].get('typ')} | Nr {liste[i].get('rechnungsnummer') or '-'}"
                     f" | Zahlung {liste[i].get('zahlung') or '?'} | Steuer: {liste[i]['steuer'].get('art') if liste[i].get('steuer', {}).get('relevant') else '-'}"
                     f" | Notiz: {liste[i].get('notiz') or '-'} | {(liste[i].get('inhalt') or '')[:300]}" for i in treffer)
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
    geaendert = aenderungen_anwenden(liste, a.get("aenderungen"))
    if geaendert:
        json_schreiben(VERZEICHNIS, liste)
        logbuch("Per Telegram geändert: " + "; ".join(geaendert))
    senden(chat, "📁 " + (a.get("antwort") or "Dazu habe ich nichts gefunden.") +
           (("\n📝 Gemerkt bei: " + "; ".join(geaendert)) if geaendert else ""))
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
    elif re.match(r"^(schreiben|brief)\b", t):
        schreiben({"chat": chat, "id": None, "text": re.sub(r"^/?(schreiben|brief)\s*[:,-]?\s*", "", text, flags=re.I)})
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
    if was == "lesen" and eintrag:
        # PDF in Stücken über die Home-Assistant-Verbindung (der Medien-Weg liefert keine PDFs aus)
        pfad = os.path.join(ABLAGE, eintrag.get("datei", ""))
        ab = max(0, int(auftrag.get("ab") or 0))
        with open(pfad, "rb") as f:
            f.seek(ab)
            roh = f.read(150_000)   # Base64 ca. 200 000 Zeichen
        gesamt = os.path.getsize(pfad)
        return {"ok": True, "daten": base64.b64encode(roh).decode("ascii"), "gesamt": gesamt, "ende": ab + len(roh) >= gesamt}
    if was == "ansehen" and eintrag:
        import shutil
        os.makedirs(ANSICHT, exist_ok=True)
        for alt in os.listdir(ANSICHT):
            if time.time() - os.path.getmtime(os.path.join(ANSICHT, alt)) > 3600:
                _weg(os.path.join(ANSICHT, alt))
        name = uuid.uuid4().hex + ".pdf"
        shutil.copyfile(os.path.join(ABLAGE, eintrag.get("datei", "")), os.path.join(ANSICHT, name))
        return {"ok": True, "datei": "akte/_ansicht/" + name}
    if was == "einstellungen":
        return {"ok": True, "einstellungen": einstellungen()}
    if was == "einstellungen_speichern":
        try:
            d = json.loads(auftrag.get("text") or "{}")
        except ValueError:
            return {"ok": False, "fehler": "ungültig"}
        ordner = [{"name": str(o.get("name"))[:60].strip(), "beschreibung": str(o.get("beschreibung") or "")[:300].strip()}
                  for o in d.get("ordner") or [] if isinstance(o, dict) and str(o.get("name") or "").strip()]
        json_schreiben(EINSTELLUNGEN, {"ordner": ordner, "hinweise": str(d.get("hinweise") or "")[:3000]})
        logbuch("Ordner und Hinweise gespeichert")
        return {"ok": True, "einstellungen": einstellungen()}
    if was == "alle_neu":
        im_hintergrund(alle_neu_lesen, {"chat": auftrag.get("chat")})
        return {"ok": True}
    if was == "wappen":
        try:
            wappen_speichern(base64.b64decode(auftrag.get("text") or ""))
            logbuch("Familienwappen gespeichert")
            return {"ok": True}
        except Exception as fehler:  # noqa: BLE001
            return {"ok": False, "fehler": str(fehler)[:120]}
    if was == "teilen" and eintrag:
        im_hintergrund(teilen, auftrag)
        return {"ok": True}
    if was == "schreiben":
        im_hintergrund(schreiben, auftrag)
        return {"ok": True}
    if was == "ordner_setzen" and eintrag:
        eintrag["ordner"], eintrag["ordner_fest"] = ordner_name(auftrag.get("ordner")), True
        if eintrag.get("frage"):
            eintrag.update({"frage": "", "vorschlaege": [], "beantwortet": True})
        datei_einordnen(eintrag)
        json_schreiben(VERZEICHNIS, liste)
        logbuch(f"In Ordner „{eintrag['ordner']}“: {eintrag.get('titel')}")
    elif was == "ordner_umbenennen":
        alt, neu = auftrag.get("id") or "", ordner_name(auftrag.get("ordner"))
        if alt and neu and alt != neu:
            for x in liste:
                o = x.get("ordner") or ""
                if o == alt or o.startswith(alt + " / "):
                    x["ordner"] = neu + o[len(alt):]
                    datei_einordnen(x)
            json_schreiben(VERZEICHNIS, liste)
            logbuch(f"Ordner „{alt}“ heißt jetzt „{neu}“")
    elif was == "antwort" and eintrag:
        antwort = (auftrag.get("text") or "").strip()[:300]
        frage = eintrag.get("frage") or ""
        if auftrag.get("ordner"):
            eintrag["ordner"], eintrag["ordner_fest"] = ordner_name(auftrag["ordner"]), True
            datei_einordnen(eintrag)
        teile = [t for t in [antwort, ("Ordner: " + eintrag["ordner"]) if auftrag.get("ordner") else ""] if t]
        if teile:
            eintrag["notiz"] = ((eintrag.get("notiz") or "") + " · " if eintrag.get("notiz") else "") + \
                               (f"Auf „{frage}“: " if frage else "") + ", ".join(teile)
        eintrag.update({"frage": "", "vorschlaege": [], "beantwortet": True})
        json_schreiben(VERZEICHNIS, liste)
        logbuch(f"Rückfrage beantwortet: {eintrag.get('titel')}")
        im_hintergrund(neu_lesen, {"id": eintrag["id"]})
    elif was == "notiz" and eintrag:
        eintrag["notiz"] = (auftrag.get("text") or "").strip()[:500]
        json_schreiben(VERZEICHNIS, liste)
        logbuch(f"Notiz: {eintrag.get('titel')}")
        if eintrag["notiz"]:
            im_hintergrund(neu_lesen, {"id": eintrag["id"]})
    elif was in ("bezahlt", "unbezahlt") and eintrag:
        eintrag["zahlung"], eintrag["zahlung_fest"] = ("bezahlt" if was == "bezahlt" else "offen"), True
        json_schreiben(VERZEICHNIS, liste)
    elif was in ("eingereicht", "offen") and eintrag and eintrag.get("einreichen", {}).get("noetig"):
        eintrag["einreichen"].update({"status": was, "am": date.today().isoformat() if was == "eingereicht" else ""})
        json_schreiben(VERZEICHNIS, liste)
    elif was == "loeschen" and eintrag:
        _weg(os.path.join(ABLAGE, eintrag.get("datei", "")))
        for s in eintrag.get("seiten") or []:
            _weg(os.path.join(SEITEN, s))
        liste.remove(eintrag)
        json_schreiben(VERZEICHNIS, liste)
    felder = ("id", "titel", "typ", "kategorie", "absender", "datum", "betrag", "person", "steuer", "einreichen", "fristen",
              "schlagworte", "von", "eingang", "notiz", "zahlung", "mahnung", "rechnungsnummer", "ordner", "frage", "vorschlaege")
    aus = [dict({k: e.get(k) for k in felder}, kurz=(e.get("inhalt") or "")[:500]) for e in liste]
    aus.sort(key=lambda e: (e.get("datum") or "", e.get("eingang") or ""), reverse=True)
    wartend = 0
    for d in (EINGANG, ORDNER, UPLOAD):
        try:
            wartend += len([n for n in os.listdir(d) if not n.startswith((".", "_"))])
        except OSError:
            pass
    log = json_laden(LOGBUCH, [])
    return {"ok": True, "eintraege": aus, "wartend": wartend, "log": list(reversed(log if isinstance(log, list) else []))[:8]}


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
        with Sperre():
            funktion(auftrag)
    except Exception as fehler:  # noqa: BLE001
        logbuch(f"Fehler: {type(fehler).__name__}: {str(fehler)[:150]}", "fehler")
        try:
            for c in ([auftrag.get("chat")] if auftrag.get("chat") else auftrag.get("chats") or [])[:1]:
                senden(c, f"⚠️ Akte: Das hat nicht geklappt ({type(fehler).__name__}: {str(fehler)[:200]}). Bitte nochmal versuchen.")
        except Exception:  # noqa: BLE001
            pass
    os._exit(0)


ORDNER = "/media/Akte-Eingang/"   # Ablage ohne Telegram: Dateien über Home Assistant → Medien hochladen


def ordner_einlesen(auftrag):
    """Alles aus dem Ordner Akte-Eingang nacheinander ablegen (Antwort an den ersten Telegram-Empfänger)."""
    chats = [c for c in auftrag.get("chats") or [] if str(c).lstrip("-").isdigit()]
    chat = chats[0] if chats else None
    for pfad in auftrag.get("dateien") or []:
        try:
            ablegen({"datei": pfad, "chat": chat, "von": "Hochgeladen", "text": ""})
        except Exception as fehler:  # noqa: BLE001
            logbuch(f"Fehler bei {os.path.basename(pfad)}: {str(fehler)[:150]}", "fehler")
            senden(chat, f"⚠️ Akte: {os.path.basename(pfad)} ging nicht ({str(fehler)[:150]}).")
    if len(auftrag.get("dateien") or []) > 1:
        try:
            durchsicht({"chat": chat})
        except Exception as fehler:  # noqa: BLE001
            logbuch(f"Fehler bei der Durchsicht: {str(fehler)[:150]}", "fehler")


def ordner_pruefen(auftrag):
    """Schnell: liegen neue Dateien im Ordner? Dann in den Eingang holen und im Hintergrund ablegen."""
    os.makedirs(ORDNER, exist_ok=True)
    dateien = []
    for n in sorted(os.listdir(ORDNER)):
        pfad = os.path.join(ORDNER, n)
        endung = n.lower().rsplit(".", 1)[-1] if "." in n else ""
        if not os.path.isfile(pfad) or time.time() - os.path.getmtime(pfad) < 20:
            continue   # noch beim Hochladen
        if endung not in ("pdf", "jpg", "jpeg", "png"):
            continue
        ziel = os.path.join(EINGANG, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.{'pdf' if endung == 'pdf' else 'jpg'}")
        if endung == "png":
            from PIL import Image
            Image.open(pfad).convert("RGB").save(ziel, "JPEG", quality=90)
            _weg(pfad)
        else:
            os.replace(pfad, ziel)
        dateien.append(ziel)
    # hängengebliebene Dateien im Eingang (z. B. nach einem Fehler) nach 15 Minuten nochmal versuchen, höchstens dreimal
    zaehler_pfad = os.path.join(EINGANG, ".versuche.json")
    zaehler = json_laden(zaehler_pfad, {})
    for n in sorted(os.listdir(EINGANG)):
        pfad = os.path.join(EINGANG, n)
        if n.startswith(".") or not os.path.isfile(pfad) or pfad in dateien or time.time() - os.path.getmtime(pfad) < 900:
            continue
        zaehler[n] = zaehler.get(n, 0) + 1
        if zaehler[n] > 3:
            os.makedirs(os.path.join(EINGANG, "_fehler"), exist_ok=True)
            os.replace(pfad, os.path.join(EINGANG, "_fehler", n))
            zaehler.pop(n, None)
            continue
        os.utime(pfad)   # erst in 15 Minuten wieder an der Reihe
        dateien.append(pfad)
    json_schreiben(zaehler_pfad, zaehler)
    if dateien:
        auftrag["dateien"] = dateien
        im_hintergrund(ordner_einlesen, auftrag)
    return len(dateien)


UPLOAD = "/media/akte/_upload/"


def stueck(argumente):
    """Hochladen über die Akte-Seite: Datei kommt in Stücken (Base64), das letzte Stück setzt sie zusammen."""
    kennung, teil, name_b64, letzt = argumente[:4]
    if not re.match(r"^[a-z0-9]{8,40}$", kennung) or not teil.isdigit():
        return {"ok": False, "fehler": "ungültig"}
    ordner = os.path.join(UPLOAD, kennung)
    os.makedirs(ordner, exist_ok=True)
    with open(os.path.join(ordner, f"{int(teil):05d}"), "w", encoding="ascii") as f:
        f.write("".join(argumente[4:]))
    if letzt != "1":
        return {"ok": True}
    import shutil
    teile = sorted(os.listdir(ordner))
    daten = "".join(open(os.path.join(ordner, t), encoding="ascii").read() for t in teile)
    shutil.rmtree(ordner, ignore_errors=True)
    roh = base64.b64decode(daten)
    if len(roh) > 40_000_000:
        return {"ok": False, "fehler": "Datei zu groß (höchstens 40 MB)"}
    name = base64.urlsafe_b64decode(name_b64 + "=" * (-len(name_b64) % 4)).decode("utf-8", "replace")
    endung = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if roh[:4] == b"%PDF":
        endung = "pdf"
    elif endung not in ("jpg", "jpeg", "png"):
        return {"ok": False, "fehler": "Nur PDF, JPG oder PNG"}
    os.makedirs(ORDNER, exist_ok=True)
    ziel = os.path.join(ORDNER, sicherer_name(name.rsplit(".", 1)[0], 60) + "_" + uuid.uuid4().hex[:4] + "." + endung)
    with open(ziel, "wb") as f:
        f.write(roh)
    alt = time.time() - 60   # gleich abholbar (der Ordner-Abholer wartet sonst 20 Sekunden)
    os.utime(ziel, (alt, alt))
    return {"ok": True, "fertig": True}


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
    if aktion == "stueck":
        print(json.dumps(stueck(sys.argv[2:]), ensure_ascii=False))
        return
    auftrag = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8")) if len(sys.argv) > 2 else {}
    for d in (ABLAGE, EINGANG, SEITEN):
        os.makedirs(d, exist_ok=True)
    umziehen()
    if aktion == "ordner":
        print(json.dumps({"ok": True, "neu": ordner_pruefen(auftrag)}))
        return
    if aktion == "seite":
        print(json.dumps(seite(auftrag), ensure_ascii=False))
        return
    funktion = {"neu": ablegen, "befehl": befehl, "erinnerung": erinnerung, "ankuendigen": ankuendigen,
                "durchsicht": durchsicht, "einmalig_neu": einmalig_neu}.get(aktion)
    if not funktion:
        print(json.dumps({"ok": False, "fehler": "unbekannte Aktion"}))
        return
    im_hintergrund(funktion, auftrag)
    time.sleep(0.2)
    print(json.dumps({"ok": True}))


if __name__ == "__main__":
    main()
