"""Nebenkostenabrechnung für den Mieter (PDF, A4 hoch) – verständlich, ohne OLMESS-Fachbegriffe.

Gleiche Rechnung wie der Ergebnis-Kasten auf der Nebenkosten-Seite (www/nebenkosten.js, ergebnisKarte):
- Kosten je Posten aus Brennstoff, Heiznebenkosten und Betriebskosten des Zeitraums.
- Fehlt ein üblicher Posten, wird der letzte bekannte Betrag aus einem früheren Zeitraum genommen (als geschätzt markiert).
- Verteilung vorläufig nach Wohnfläche (Schlüssel S005 = je Wohnung), anteilig nach Mietdauer im Zeitraum.
- CO2-Kosten: Vermieteranteil nach dem Stufenmodell des CO2-Kostenaufteilungsgesetzes.
"""
import re
from datetime import date

import nk_pdf
from nk_pdf import Blatt, _de, _zahl, _wert, GRAU, AKZENT

POSTEN = [
    ("Gas (Heizung + Warmwasser)", "heiz", lambda x, l: l == "brennstoff"),
    ("Heizungs- und Allgemeinstrom", "heiz", lambda x, l: re.search(r"strom", x.get("art") or "", re.I)),
    ("Schornsteinfeger", "heiz", lambda x, l: re.search(r"schornstein", x.get("art") or "", re.I)),
    ("Wartung Heizung", "heiz", lambda x, l: re.search(r"wartung", x.get("art") or "", re.I)),
    ("Grundsteuer", "betrieb", lambda x, l: re.search(r"grundsteuer", x.get("art") or "", re.I)),
    ("Müllabfuhr", "betrieb", lambda x, l: re.search(r"abfall|müll", x.get("art") or "", re.I)),
    ("Straßenreinigung", "betrieb", lambda x, l: re.search(r"stra(ß|ss)enrein", x.get("art") or "", re.I)),
    ("Frischwasser", "betrieb", lambda x, l: re.search(r"frischwasser|trinkwasser|wasserversorgung|wasserlieferung", x.get("art") or "", re.I)),
    ("Abwasser", "betrieb", lambda x, l: re.search(r"abwasser|schmutzwasser", x.get("art") or "", re.I)),
    ("Regenwasser (Niederschlag)", "betrieb", lambda x, l: re.search(r"niederschlag|regenwasser|oberfl", x.get("art") or "", re.I)),
    ("Gebäudeversicherung", "betrieb", lambda x, l: re.search(r"geb(ä|ae)ude|feuer|elementar", x.get("art") or "", re.I)),
    ("Haftpflichtversicherung", "betrieb", lambda x, l: re.search(r"haftpflicht", x.get("art") or "", re.I)),
]
STUFEN = [(12, 0), (17, 10), (22, 20), (27, 30), (32, 40), (37, 50), (42, 60), (47, 70), (52, 80), (1e9, 95)]


def _dez(x):
    """Wie _wert, aber "78.63" ist 78,63 (nicht 7863)."""
    t = str(x if x is not None else "").strip()
    if re.fullmatch(r"-?\d+\.\d{1,2}", t):
        return float(t)
    return _wert(x)


def posten_von(z):
    aus = {}
    for l in ("brennstoff", "heizneben", "betrieb"):
        for x in z.get(l) or []:
            if x.get("brutto") in ("", None):
                continue
            p = next((p for p in POSTEN if p[2](x, l)), None) or (
                ("Sonstige Betriebskosten", "betrieb") if l == "betrieb" else ("Sonstige Heizkosten", "heiz"))
            e = aus.setdefault(p[0], {"summe": 0.0, "gruppe": p[1], "bs": x.get("bs")})
            e["summe"] += _dez(x.get("brutto"))
    return aus


def berechnen(name, z, frueher):
    """frueher: {zeitraum_name: daten} älterer Zeiträume. Gibt je Mieter ein Ergebnis zurück."""
    ein = z.get("einheiten") or []
    gesamt_f = sum(_dez(e.get("hz_flaeche")) for e in ein)
    mieter = [e for e in ein if e.get("nutzer") and not re.search(r"ferien|selbst|leer|eigen", f"{e.get('nutzung', '')} {e.get('nutzer', '')}", re.I)]
    jetzt = posten_von(z)
    alt = [(n, posten_von(frueher[n])) for n in sorted(frueher, reverse=True) if n < name]
    zeilen = []
    for pname, gruppe, _ in POSTEN:
        if pname in jetzt:
            zeilen.append(dict(name=pname, gruppe=gruppe, summe=jetzt[pname]["summe"], bs=jetzt[pname]["bs"], art="da"))
            continue
        f = next(((n, p) for n, p in alt if pname in p), None)
        zeilen.append(dict(name=pname, gruppe=gruppe, summe=f[1][pname]["summe"], bs=f[1][pname]["bs"], art="schaetzung",
                           aus=f"{f[0][:4]}/{f[0][13:15]}") if f else dict(name=pname, gruppe=gruppe, summe=0.0, art="fehlt"))
    for pname, v in jetzt.items():
        if not any(p[0] == pname for p in POSTEN):
            zeilen.append(dict(name=pname, gruppe=v["gruppe"], summe=v["summe"], bs=v["bs"], art="da"))
    von, bis = date.fromisoformat(z["von"]), date.fromisoformat(z["bis"])
    tage_z = (bis - von).days + 1
    co2 = _dez((z.get("abgaben") or {}).get("co2"))
    kwh = sum(_dez(x.get("kwh")) for x in z.get("brennstoff") or [])
    kg_m2 = kwh * 0.181 / gesamt_f if kwh and gesamt_f else 0
    verm_co2 = next(p for g, p in STUFEN if kg_m2 < g) if kwh else 0
    ergebnisse = []
    for m in mieter:
        a = max(von, date.fromisoformat(m["einzug"])) if m.get("einzug") else von
        b = min(bis, date.fromisoformat(m["auszug"])) if m.get("auszug") else bis
        zeit = max(0, (b - a).days + 1) / tage_z
        anteil = _dez(m.get("hz_flaeche")) / gesamt_f * zeit if gesamt_f else 0
        reihen = []
        for x in zeilen:
            f = zeit / len(ein) if x.get("bs") == "S005" else anteil
            reihen.append(dict(x, faktor=f, betrag=x["summe"] * f))
        co2_weg = co2 * anteil * verm_co2 / 100
        kosten = sum(r["betrag"] for r in reihen) - co2_weg
        vz = _dez(m.get("vz_neben")) + _dez(m.get("vz_heizung"))
        monate = max(1, round(zeit * 12))
        ergebnisse.append(dict(mieter=m, anteil=anteil, zeit=zeit, monate=monate, reihen=reihen, co2_weg=co2_weg, verm_co2=verm_co2,
                               kg_m2=kg_m2, kosten=kosten, vz=vz, diff=kosten - vz, gesamt_f=gesamt_f,
                               fehlt=[r["name"] for r in reihen if r["art"] == "fehlt"],
                               geschaetzt=[r["name"] for r in reihen if r["art"] == "schaetzung"]))
    return ergebnisse


def erstellen(pfad, name, z, frueher, frist_iso):
    ergebnisse = berechnen(name, z, frueher)
    if not ergebnisse:
        raise ValueError("Kein Mieter in der Nutzerliste")
    e = ergebnisse[0]
    m = e["mieter"]
    zeitraum = f"{_de(z['von'])} – {_de(z['bis'])}"
    vorlaeufig = bool(e["fehlt"] or e["geschaetzt"])
    abgelaufen = bool(frist_iso) and date.fromisoformat(frist_iso) < date.today()
    p = Blatt((f"Nebenkostenabrechnung {zeitraum}",
               f"{z.get('objekt', '')} · Wohnung {m.get('lage', '')} · Mieterin/Mieter: {m.get('nutzer', '')} · Vermieter: {z.get('eigentuemer', '')}"),
              hochformat=True)
    if vorlaeufig or abgelaufen:
        p.flaeche(nk_pdf.RAND, p.y - 30, p.W - 2 * nk_pdf.RAND, 40, "1 0.96 0.84")
        p.y -= 2
        p.t(nk_pdf.RAND + 8, p.y, 10, "Vorläufige Übersicht zur Information – keine Zahlungsaufforderung." if vorlaeufig or (abgelaufen and e["diff"] > 0)
            else "Abrechnung zur Information.", fett=True)
        p.y -= 13
        p.t(nk_pdf.RAND + 8, p.y, 8.5, ("Einige Rechnungen liegen noch nicht vor (siehe unten). " if vorlaeufig else "")
            + ("Für diesen Zeitraum wird keine Nachzahlung verlangt." if abgelaufen and e["diff"] > 0 else ""))
        p.y -= 26

    p.ueberschrift("Ergebnis")
    p.t(nk_pdf.RAND, p.y, 16, ("Zwischenstand – " if e["fehlt"] else "") + f"{'Nachzahlung' if e['diff'] >= 0 else 'Guthaben'}: {_zahl(abs(e['diff']))} €",
        fett=True, farbe=AKZENT)
    p.y -= 20
    if e["fehlt"]:
        p.absatz(f"Noch nicht enthalten: {', '.join(e['fehlt'])}. Dadurch steigen die Kosten noch – das Endergebnis folgt, "
                 "sobald alle Rechnungen vorliegen.", 9.5)
    p.absatz(f"Ihre Kosten im Zeitraum: {_zahl(e['kosten'])} € (das sind {_zahl(e['kosten'] / e['monate'])} € im Monat). "
             f"Gezahlt haben Sie {_zahl(e['vz'])} € Vorauszahlung ({_zahl(e['vz'] / e['monate'])} € im Monat).", 10)

    p.ueberschrift("Ihr Anteil")
    p.absatz(f"Ihre Wohnfläche: {_zahl(_dez(m.get('hz_flaeche')))} m² von {_zahl(e['gesamt_f'])} m² im ganzen Haus = "
             f"{_zahl(e['anteil'] / e['zeit'] * 100 if e['zeit'] else 0, 1)} %. Mietdauer im Zeitraum: {e['monate']} Monate.", 9.5)

    p.ueberschrift("Kosten des Hauses und Ihr Anteil", "alle Beträge brutto")
    zeilen = []
    for gruppe, titel in (("heiz", "Heizung und Warmwasser"), ("betrieb", "Betriebskosten")):
        for r in [r for r in e["reihen"] if r["gruppe"] == gruppe]:
            if r["art"] == "fehlt":
                zeilen.append([r["name"], "Rechnung folgt", "", "–"])
                continue
            vert = "je Wohnung" if r.get("bs") == "S005" else "nach Wohnfläche"
            zeilen.append([r["name"] + (f" (geschätzt wie {r['aus']})" if r["art"] == "schaetzung" else ""),
                           _zahl(r["summe"]), f"{vert}, {_zahl(r['faktor'] * 100, 1)} %", _zahl(r["betrag"])])
    if e["co2_weg"]:
        zeilen.append([f"abzüglich CO2-Kosten, die der Vermieter trägt ({e['verm_co2']} %)", "", f"ca. {_zahl(e['kg_m2'], 1)} kg CO2/m²",
                       "- " + _zahl(e["co2_weg"])])
    p.tabelle([("Posten", 78, False), ("Haus gesamt €", 28, True), ("Verteilung", 46, False), ("Ihr Anteil €", 28, True)],
              zeilen, ["Ihre Kosten", "", "", _zahl(e["kosten"])])
    p.tabelle([("Abrechnung", 152, False), ("€", 28, True)],
              [["Ihre Kosten im Zeitraum", _zahl(e["kosten"])],
               [f"abzüglich Ihrer Vorauszahlungen ({e['monate']} × {_zahl(e['vz'] / e['monate'])} €)", "- " + _zahl(e["vz"])]],
              ["Nachzahlung" if e["diff"] >= 0 else "Guthaben", _zahl(abs(e["diff"]))])

    p.ueberschrift("Erläuterungen")
    p.absatz("• Heizung und Warmwasser kommen aus einer gemeinsamen Gasheizung für beide Wohnungen. Nach der Heizkostenverordnung "
             "wird die Hälfte nach Wohnfläche und die Hälfte nach den Wärmezählern verteilt. In dieser Übersicht ist vorläufig alles nach "
             "Wohnfläche verteilt; mit den Zählerständen kann sich Ihr Anteil noch etwas ändern.")
    p.absatz("• CO2-Kosten: Seit 2023 trägt der Vermieter einen Teil der CO2-Kosten für das Gas (Kohlendioxidkostenaufteilungsgesetz). "
             "Der Anteil richtet sich nach dem CO2-Ausstoß des Hauses je m² Wohnfläche und ist oben schon abgezogen.")
    p.absatz("• Die Gasrechnungen des Versorgers laufen von Mitte Januar bis Mitte Januar. Die Kosten wurden tageweise auf den "
             "Abrechnungszeitraum umgerechnet.")
    if e["fehlt"] or e["geschaetzt"]:
        p.absatz("• Noch nicht vorliegende Rechnungen: " + ", ".join(e["geschaetzt"] + e["fehlt"]) + ". Geschätzte Posten sind mit dem "
                 "Betrag aus einem Vorjahr angesetzt, fehlende sind noch nicht enthalten.")
    p.absatz("• Die Rechnungen und Belege können Sie gern einsehen. Einwände gegen die Abrechnung bitte innerhalb von 12 Monaten "
             "nach Erhalt mitteilen.")
    if e["diff"] > 0 and not vorlaeufig and not abgelaufen:
        neu = -(-e["kosten"] / e["monate"] // 5) * 5
        p.absatz(f"• Damit es im nächsten Jahr passt, wird die monatliche Vorauszahlung auf {_zahl(neu)} € angepasst.")
    p.speichern(pfad)
    return e
