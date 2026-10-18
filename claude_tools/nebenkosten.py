"""Nebenkostenabrechnung (Teil der digitalen Akte): sammelt je Abrechnungszeitraum alles, was der Abrechnungsdienst
(OLMESS) für Heizkosten- und Betriebskostenabrechnung braucht – Brennstoff, Heiznebenkosten, Betriebskosten mit
Verteilerschlüssel, Nutzerliste (Fläche, Personen, Vorauszahlungen) und Zählerstände.

- Werte trägt die Familie auf der Akte-Seite ein (Reiter "Nebenkosten") oder Claude übernimmt sie aus den Belegen der Akte
  ("Aus Belegen übernehmen"); Vorschläge sind markiert und lassen sich ändern oder löschen.
- Zählerfotos liest Claude selbst (Zählerart, Nummer, Stand, Stichtag).
- "Als PDF" setzt alles in der Reihenfolge der OLMESS-Bögen zusammen und schickt es per Telegram.
Daten: /config/nebenkosten.json und /config/nebenkosten_fotos/ – nur lokal, nie im Repository."""
import base64
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta

import akte

DATEI = "/config/nebenkosten.json"
FOTOS = "/config/nebenkosten_fotos/"
ABLAGE = "/config/akte_ablage/Nebenkosten/"

# Verteilerschlüssel laut Betriebskostenaufstellung von OLMESS
SCHLUESSEL = {"S005": "Anzahl WE", "S006": "Anzahl Nutzer", "S015": "Personen", "S021": "HZ pauschal", "S022": "WW pauschal",
              "S023": "HZ Festbetrag", "S024": "WW Festbetrag", "S030": "HZ Fläche", "S031": "WW Fläche", "S032": "HN Fläche",
              "S050": "Wasser gesamt", "S051": "Kaltwasser", "S052": "Warmwasser"}
HH_TYPEN = {"1": "geringfügige Beschäftigung", "2": "sozialvers.-pfl. Beschäftigung", "3": "Dienstleistung", "4": "Handwerker"}


def zeitraum_name(von, bis):
    return f"{von}_{bis}"


def standard(von, bis, vorher=None):
    """Neuer Abrechnungszeitraum; Nutzerliste (Lage, Flächen …) aus dem Zeitraum davor übernehmen."""
    einheiten = [dict(e, vz_heizung="", vz_neben="") for e in (vorher or {}).get("einheiten") or []] or [
        {"nr": "0010-001", "lage": "EG", "nutzung": "Ferienwohnung", "nutzer": "", "einzug": "", "auszug": "",
         "hz_flaeche": "", "ww_flaeche": "", "personen": "", "vz_heizung": "", "vz_neben": ""},
        {"nr": "0020-001", "lage": "OG", "nutzung": "", "nutzer": "", "einzug": "", "auszug": "",
         "hz_flaeche": "", "ww_flaeche": "", "personen": "", "vz_heizung": "", "vz_neben": ""}]
    return {"von": von, "bis": bis, "objekt": (vorher or {}).get("objekt") or "Nadorster Straße 299, 26125 Oldenburg",
            "eigentuemer": (vorher or {}).get("eigentuemer") or "Marco Schlag",
            "liegenschaft": (vorher or {}).get("liegenschaft") or "1-200167",
            "einheiten": einheiten, "brennstoff": [], "abgaben": {"co2": "", "energiesteuer": "", "netzentgelt": "", "weitere": ""},
            "heizneben": [], "betrieb": [], "wasser_cbm": "",
            "zaehler": [dict(z, staende=[]) for z in (vorher or {}).get("zaehler") or []],
            "hinweise": [], "status": "", "notiz": ""}


def alle():
    d = akte.json_laden(DATEI, {})
    if not isinstance(d, dict) or not isinstance(d.get("zeitraeume"), dict):
        d = {"zeitraeume": {}}
    if not d["zeitraeume"]:
        # erster Start: der Zeitraum der vorliegenden OLMESS-Bögen und der folgende
        d["zeitraeume"]["2023-11-01_2024-10-31"] = standard("2023-11-01", "2024-10-31")
        d["zeitraeume"]["2024-11-01_2025-10-31"] = standard("2024-11-01", "2025-10-31")
    return d


def frist(z):
    """Spätestens 12 Monate nach Ende des Abrechnungszeitraums muss die Abrechnung beim Mieter sein (§ 556 Abs. 3 BGB)."""
    try:
        bis = date.fromisoformat(z["bis"])
        return date(bis.year + 1, bis.month, bis.day).isoformat()
    except (KeyError, ValueError):
        return ""


def zahl(x):
    try:
        return float(str(x).replace(".", "").replace(",", ".")) if isinstance(x, str) and "," in x else float(x)
    except (TypeError, ValueError):
        return None


# ---------- Belege der Akte auswerten ----------

AUSWAHL = """Du hilfst einer Familie bei der Heiz- und Betriebskostenabrechnung für ihr Mietshaus (Objekt unten, zwei Wohnungen:
EG Ferienwohnung, OG). Unten steht die Liste ihrer digitalen Akte. Suche ALLE Belege heraus, die Kosten des GANZEN Hauses im
Abrechnungszeitraum betreffen könnten: Gas/Erdgas (Jahresrechnung des Versorgers), Heizungswartung, Schornsteinfeger,
Heizstrom/Allgemeinstrom, Wasser/Abwasser, Niederschlagswasser, Müll/Abfall, Straßenreinigung, Grundsteuer (Bescheid),
Gebäude-/Haftpflichtversicherung, Gartenpflege, Hausreinigung, Rauchmelder-/Zählermiete, Ablesedienst (OLMESS), Winterdienst.
Auch Belege, die etwas später kommen (Jahresrechnungen nach Ende des Zeitraums) oder Bescheide für das ganze Jahr.
Nicht: Belege eines anderen Objekts (z. B. Hof Fünfhauser Weg), private Belege, reine Abschlagspläne ohne Jahresabrechnung.
Antworte NUR mit JSON: {"nummern": [Nummern], "fehlt": ["typische Kostenarten, für die kein Beleg in der Liste steht, z. B.
"Grundsteuerbescheid", "Wasserrechnung"]}"""

AUSWERTEN = """Du bereitest für eine Familie die Angaben für den Abrechnungsdienst OLMESS vor (Heizkostenaufstellung und
Betriebskostenaufstellung, alle Beträge brutto inkl. MwSt.). Objekt und Abrechnungszeitraum stehen unten, die Belege hängen
an (Nummer steht davor). Regeln:
- Brennstoff (Erdgas): nur aus Jahres-/Schlussrechnungen des Versorgers: Datum, kWh, Bruttobetrag für den Verbrauch im
  Abrechnungszeitraum. Weicht der Rechnungszeitraum ab, tageweise anteilig umrechnen und das im Feld "hinweis" sagen.
  Abschlagszahlungen sind keine Kosten. Aus der Gasrechnung auch CO2-Kosten, Energiesteuer, Netzentgelt (brutto, für den
  Zeitraum) in "abgaben" (Zahlen, Summe über alle Gasrechnungen).
- Heiznebenkosten: Wartung/Reinigung der Heizung, Schornsteinfeger (Mess-/Kehrgebühren), Betriebsstrom der Heizung,
  Ablese-/Mietkosten der Wärmezähler/Heizkostenverteiler, Wasserzähler-Miete für Warmwasser.
- Betriebskosten (nur umlagefähige nach § 2 BetrKV): Grundsteuer, Wasser/Abwasser, Niederschlagswasser, Müll,
  Straßenreinigung, Gebäude-/Haftpflichtversicherung, Allgemeinstrom, Gartenpflege, Hausreinigung, Schornsteinfeger
  (falls nicht Heizung), Rauchmelder-Wartung, Winterdienst. NICHT: Reparaturen, Instandhaltung, Verwaltung, Bankgebühren,
  Kosten nur der Ferienwohnung (Reinigung FeWo, Internet, Portalgebühren). Jahresbeträge anteilig auf den Zeitraum.
- Verteilerschlüssel "bs" für Betriebskosten: S032 (Wohnfläche) für Grundsteuer, Versicherung, Allgemeinstrom, Garten,
  Reinigung; S050 (Wasser gesamt) für Wasser/Abwasser, wenn Wohnungs-Wasserzähler da sind, sonst S015 (Personen);
  S015 für Müll; S005 (Anzahl Wohnungen) für Pauschalen je Wohnung.
- "hhdl": Anteil Arbeits-/Dienstleistungskosten brutto für haushaltsnahe Dienstleistungen/Handwerker (z. B. Schornsteinfeger,
  Wartung, Gartenpflege, Reinigung) mit "hhtyp" 3 (Dienstleistung) oder 4 (Handwerker); sonst leer.
- "mwst": Steuersatz in Prozent laut Beleg (19, 7 oder 0).
- Wasser: Gesamtmenge laut Wasserversorger in m³ für den Zeitraum in "wasser_cbm".
- Datum JJJJ-MM-TT (Rechnungs-/Bescheiddatum). Nichts erfinden: Was nicht im Beleg steht, leer lassen.
Antworte NUR mit JSON: {"brennstoff": [{"datum": "", "kwh": Zahl, "brutto": Zahl, "beleg": Nummer, "hinweis": ""}],
 "abgaben": {"co2": Zahl|null, "energiesteuer": Zahl|null, "netzentgelt": Zahl|null, "weitere": Zahl|null},
 "heizneben": [{"art": "", "datum": "", "brutto": Zahl, "mwst": Zahl, "hhdl": Zahl|null, "hhtyp": "3"|"4"|"", "beleg": Nummer, "hinweis": ""}],
 "betrieb": [{"art": "", "bs": "S032", "datum": "", "brutto": Zahl, "mwst": Zahl, "hhdl": Zahl|null, "hhtyp": "", "beleg": Nummer, "hinweis": ""}],
 "wasser_cbm": Zahl|null, "hinweise": ["kurze Hinweise: Anteilige Umrechnungen, Unklarheiten, nicht umlagefähige Posten"]}"""

ZAEHLER = """Auf dem Foto ist ein Zähler (Wasser, Wärme, Gas, Strom oder Heizkostenverteiler) eines Hauses mit zwei Wohnungen
(EG Ferienwohnung, OG). Lies ihn ab. Viele Zähler zeigen auch einen Stichtagswert mit Datum (z. B. "31.10.24" / "Stichtag") –
dann diesen Wert mit seinem Datum. Antworte NUR mit JSON:
{"art": "Kaltwasser"|"Warmwasser"|"Wärmemenge"|"Gas"|"Strom"|"Heizkostenverteiler"|"Sonstiges",
 "beschriftung": "Aufschrift/Etikett am Zähler oder daneben, z. B. OG Warmwasser", "lage": "EG"|"OG"|"Haus"|"",
 "nummer": "Zähler-/Gerätenummer", "stand": Zahl (mit Nachkommastellen, rote Ziffern = Nachkommastellen), "einheit": "m³"|"kWh"|"MWh"|"Einheiten",
 "stichtag": "JJJJ-MM-TT, nur wenn das Display einen Stichtagswert mit Datum zeigt, sonst leer",
 "lesbar": true/false, "hinweis": "kurz, z. B. Display zeigt Fehlercode, Ziffern verdeckt"}"""


def _zeitraum_text(z):
    return (f"Objekt: {z.get('objekt')} (Liegenschaft {z.get('liegenschaft')}), Eigentümer {z.get('eigentuemer')}\n"
            f"Abrechnungszeitraum: {akte.de_datum(z['von'])} – {akte.de_datum(z['bis'])}\nHeute: {date.today().isoformat()}")


def auswerten(auftrag):
    """Claude sucht die passenden Belege aus der Akte und trägt die Werte als Vorschläge ein (eigene Einträge bleiben)."""
    name = auftrag.get("id")
    d = alle()
    z = d["zeitraeume"].get(name)
    if not z:
        return
    liste = akte.verzeichnis()
    von, bis = date.fromisoformat(z["von"]), date.fromisoformat(z["bis"])
    fenster = ((von - timedelta(days=120)).isoformat(), (bis + timedelta(days=300)).isoformat())
    kandidaten = [(i + 1, e) for i, e in enumerate(liste)
                  if not e.get("datum") or fenster[0] <= e["datum"] <= fenster[1] or e.get("typ") in ("Bescheid", "Versicherungspolice", "Vertrag")]
    zeilen = "\n".join(f"{nr}. {e.get('titel')} · {e.get('absender')} · {e.get('datum')} · {akte.euro(e.get('betrag'))} · "
                       f"Ordner {e.get('ordner') or '-'} · {e.get('kategorie')} · {(e.get('inhalt') or '')[:250]}" for nr, e in kandidaten)
    wahl = akte.claude(AUSWAHL, [{"type": "text", "text": _zeitraum_text(z) + "\n\nAkte:\n" + (zeilen or "(leer)")}], max_tokens=2000)
    nummern = [n for n in wahl.get("nummern") or [] if isinstance(n, int) and 1 <= n <= len(liste)][:30]
    ergebnis = {"brennstoff": [], "abgaben": {}, "heizneben": [], "betrieb": [], "wasser_cbm": None,
                "hinweise": [f"Kein Beleg gefunden für: {', '.join(wahl['fehlt'])}"] if wahl.get("fehlt") else []}
    for i in range(0, len(nummern), 6):   # höchstens 6 Belege je Anfrage
        bloecke = []
        for nr in nummern[i:i + 6]:
            e = liste[nr - 1]
            pfad = os.path.join(akte.ABLAGE, e.get("datei") or "")
            if os.path.exists(pfad):
                bloecke += [{"type": "text", "text": f"Beleg {nr}: {e.get('titel')} ({e.get('absender')}, {e.get('datum')})"
                                                    + (f" – Notiz: {e['notiz']}" if e.get("notiz") else "")}, akte.dokument_block(pfad)]
        if not bloecke:
            continue
        teil = akte.claude(AUSWERTEN, bloecke + [{"type": "text", "text": _zeitraum_text(z)}], max_tokens=6000, effort="medium")
        for feld in ("brennstoff", "heizneben", "betrieb", "hinweise"):
            ergebnis[feld] += [x for x in teil.get(feld) or [] if x]
        for k, v in (teil.get("abgaben") or {}).items():
            if zahl(v) is not None:
                ergebnis["abgaben"][k] = round((zahl(ergebnis["abgaben"].get(k)) or 0) + zahl(v), 2)
        if zahl(teil.get("wasser_cbm")) is not None:
            ergebnis["wasser_cbm"] = round((zahl(ergebnis["wasser_cbm"]) or 0) + zahl(teil["wasser_cbm"]), 2)

    # frisch laden (die Familie kann inzwischen etwas eingetragen haben) und nur die Vorschläge ersetzen
    d = alle()
    z = d["zeitraeume"].get(name)
    if not z:
        return

    def zeile(x, beleg_nr):
        e = liste[beleg_nr - 1] if isinstance(beleg_nr, int) and 1 <= beleg_nr <= len(liste) else {}
        return dict({k: ("" if v is None else v) for k, v in x.items() if k != "beleg"}, vorschlag=True,
                    beleg=e.get("id", ""), beleg_titel=" · ".join(t for t in [e.get("titel"), akte.de_datum(e.get("datum"))] if t))
    for feld in ("brennstoff", "heizneben", "betrieb"):
        z[feld] = [x for x in z.get(feld) or [] if not x.get("vorschlag")] + [zeile(x, x.get("beleg")) for x in ergebnis[feld]]
    for k, v in ergebnis["abgaben"].items():
        if k in z["abgaben"] and (not z["abgaben"][k] or z.get("abgaben_vorschlag")):
            z["abgaben"][k] = v
    z["abgaben_vorschlag"] = bool(ergebnis["abgaben"])
    if ergebnis["wasser_cbm"] is not None and (not z.get("wasser_cbm") or z.get("wasser_vorschlag")):
        z["wasser_cbm"], z["wasser_vorschlag"] = ergebnis["wasser_cbm"], True
    z["hinweise"] = [str(h)[:300] for h in ergebnis["hinweise"]][:12]
    anzahl = sum(len([x for x in z[f] if x.get("vorschlag")]) for f in ("brennstoff", "heizneben", "betrieb"))
    z["status"] = f"Aus {len(nummern)} Belegen {anzahl} Posten übernommen ({datetime.now().strftime('%d.%m. %H:%M')}) – bitte prüfen"
    akte.json_schreiben(DATEI, d)
    akte.logbuch(f"Nebenkosten: {anzahl} Posten aus der Akte übernommen")


def zaehler_lesen(auftrag):
    """Zählerfoto auswerten und als Ablesung beim passenden Zähler eintragen (neuer Zähler, wenn unbekannt)."""
    name, foto = auftrag.get("id"), os.path.basename(auftrag.get("text") or "")
    pfad = os.path.join(FOTOS, foto)
    if not os.path.exists(pfad):
        return
    w = akte.claude(ZAEHLER, [akte.dokument_block(pfad)], max_tokens=800, effort="medium")
    aufnahme = ""
    try:   # Aufnahmedatum aus dem Foto (EXIF), sonst heute
        from PIL import Image
        roh = Image.open(pfad).getexif().get(36867) or Image.open(pfad).getexif().get(306) or ""
        aufnahme = datetime.strptime(str(roh)[:10], "%Y:%m:%d").date().isoformat() if roh else ""
    except Exception:  # noqa: BLE001
        pass
    d = alle()
    z = d["zeitraeume"].get(name)
    if not z:
        return
    nummer = str(w.get("nummer") or "").strip()
    beschr = str(w.get("beschriftung") or "").strip()
    passend = next((m for m in z["zaehler"] if nummer and m.get("nummer") == nummer), None) or \
        next((m for m in z["zaehler"] if not nummer and beschr and m.get("name", "").lower() == beschr.lower()), None)
    if passend is None:
        passend = {"id": uuid.uuid4().hex[:8], "name": beschr or f"{w.get('lage') or ''} {w.get('art') or 'Zähler'}".strip(),
                   "art": w.get("art") or "", "lage": w.get("lage") or "", "nummer": nummer, "einheit": w.get("einheit") or "", "staende": []}
        z["zaehler"].append(passend)
    passend["staende"].append({"datum": w.get("stichtag") or aufnahme or date.today().isoformat(), "stand": w.get("stand"),
                               "foto": foto, "vorschlag": True, "stichtag": bool(w.get("stichtag")),
                               "hinweis": ("" if w.get("lesbar", True) else "schlecht lesbar – bitte prüfen. ") + str(w.get("hinweis") or "")})
    passend["staende"].sort(key=lambda s: s.get("datum") or "")
    akte.json_schreiben(DATEI, d)
    akte.logbuch(f"Zähler abgelesen: {passend['name']} {w.get('stand')} {passend.get('einheit') or ''}")


def foto_speichern(roh, name):
    """Zählerfoto vom Hochladen: verkleinert ablegen, Dateiname zurück."""
    from PIL import Image, ImageOps
    import io
    os.makedirs(FOTOS, exist_ok=True)
    ziel = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4] + ".jpg"
    img = Image.open(io.BytesIO(roh))
    exif = img.info.get("exif")
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((1600, 1600))
    img.save(os.path.join(FOTOS, ziel), "JPEG", quality=80, **({"exif": exif} if exif else {}))
    return ziel


def pdf_senden(auftrag):
    import nk_pdf
    d = alle()
    z = d["zeitraeume"].get(auftrag.get("id"))
    if not z:
        return
    belege = {e.get("id"): e for e in akte.verzeichnis()}
    os.makedirs(ABLAGE, exist_ok=True)
    pfad = os.path.join(ABLAGE, f"Nebenkosten_{z['von'][:4]}-{z['bis'][:4]}_Nadorster-Str.pdf")
    nk_pdf.erstellen(pfad, z, belege, SCHLUESSEL, HH_TYPEN, frist(z))
    chat = akte.chat_fuer(auftrag.get("wer"), auftrag.get("chats")) or auftrag.get("chat")
    if chat:
        akte.datei_senden(chat, pfad, f"Nebenkosten {akte.de_datum(z['von'])} – {akte.de_datum(z['bis'])}: Werte für die "
                                      "OLMESS-Bögen (Heizkosten, Betriebskosten, Nutzerliste) und die Zählerstände.")
    akte.logbuch("Nebenkosten-Übersicht als PDF verschickt")


def seite(auftrag):
    """Aufrufe von der Akte-Seite (was beginnt mit nk_)."""
    was = auftrag.get("was")
    d = alle()
    name = auftrag.get("id") or ""
    if was == "nk_neu":
        letzte = max(d["zeitraeume"].values(), key=lambda z: z["bis"])
        von = (date.fromisoformat(letzte["bis"]) + timedelta(days=1)).isoformat()
        bis = (date.fromisoformat(von).replace(year=date.fromisoformat(von).year + 1) - timedelta(days=1)).isoformat()
        name = zeitraum_name(von, bis)
        d["zeitraeume"][name] = standard(von, bis, letzte)
        akte.json_schreiben(DATEI, d)
    elif was == "nk_speichern" and name in d["zeitraeume"]:
        try:
            neu = json.loads(auftrag.get("text") or "{}")
        except ValueError:
            return {"ok": False, "fehler": "ungültig"}
        alt = d["zeitraeume"][name]
        liest = str(alt.get("status") or "").startswith("Ich lese")   # Belege werden gerade übernommen: Kosten nicht überschreiben
        for k in ("einheiten", "notiz", "objekt", "eigentuemer", "liegenschaft") + (
                () if liest else ("brennstoff", "abgaben", "heizneben", "betrieb", "wasser_cbm", "abgaben_vorschlag", "wasser_vorschlag")):
            if k in neu:
                alt[k] = neu[k]
        if isinstance(neu.get("zaehler"), list):
            # inzwischen im Hintergrund abgelesene Stände behalten, außer die Familie hat sie gelöscht
            weg_fotos, weg_zaehler = set(neu.get("geloescht_fotos") or []), set(neu.get("geloescht_zaehler") or [])
            ihre_fotos = {st.get("foto") for m in neu["zaehler"] for st in m.get("staende") or [] if st.get("foto")}
            ihre = {m.get("id"): m for m in neu["zaehler"] if m.get("id")}
            for m in alt.get("zaehler") or []:
                neue = [st for st in m.get("staende") or [] if st.get("foto") and st["foto"] not in ihre_fotos and st["foto"] not in weg_fotos]
                if not neue or m.get("id") in weg_zaehler:
                    continue
                if m.get("id") in ihre:
                    ihre[m["id"]].setdefault("staende", []).extend(neue)
                else:
                    neu["zaehler"].append(dict(m, staende=neue))
            alt["zaehler"] = neu["zaehler"]
        akte.json_schreiben(DATEI, d)
    elif was == "nk_auswerten" and name in d["zeitraeume"]:
        d["zeitraeume"][name]["status"] = "Ich lese die Belege … (dauert 1–3 Minuten)"
        akte.json_schreiben(DATEI, d)
        akte.im_hintergrund(auswerten, auftrag)
    elif was == "nk_zaehler" and name in d["zeitraeume"]:
        akte.im_hintergrund(zaehler_lesen, auftrag)
    elif was == "nk_pdf" and name in d["zeitraeume"]:
        akte.im_hintergrund(pdf_senden, auftrag)
    elif was == "nk_foto":
        pfad = os.path.join(FOTOS, os.path.basename(auftrag.get("text") or ""))
        if not os.path.exists(pfad):
            return {"ok": False}
        from PIL import Image
        import io
        img = Image.open(pfad)
        img.thumbnail((700, 700))
        puffer = io.BytesIO()
        img.convert("RGB").save(puffer, "JPEG", quality=70)
        return {"ok": True, "bild": base64.b64encode(puffer.getvalue()).decode("ascii")}
    if name not in d["zeitraeume"]:
        name = sorted(d["zeitraeume"])[0]
    return {"ok": True, "zeitraum": name, "daten": d["zeitraeume"][name], "zeitraeume": sorted(d["zeitraeume"]),
            "frist": frist(d["zeitraeume"][name]), "schluessel": SCHLUESSEL, "hh_typen": HH_TYPEN}
