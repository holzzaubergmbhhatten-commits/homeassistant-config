"""Nebenkosten-Übersicht als PDF (A4 quer) – gleiche Reihenfolge und Spalten wie die Bögen von OLMESS, damit man die Werte
1:1 übertragen oder die Übersicht mitschicken kann. Ohne Zusatzbibliotheken (Schrift Helvetica, WinAnsi)."""
import zlib
from datetime import date

from brief_pdf import _breite, _esc, _umbrechen, GRAU, DUNKEL, AKZENT

MM = 72 / 25.4
BREITE, HOEHE = 297 * MM, 210 * MM
RAND = 14 * MM


def _de(iso):
    s = str(iso or "")
    return f"{s[8:10]}.{s[5:7]}.{s[:4]}" if len(s) == 10 and s[4] == "-" else s


def _zahl(x, stellen=2):
    try:
        if isinstance(x, str):
            x = float(x.replace(".", "").replace(",", ".")) if "," in x else float(x)
        return f"{float(x):,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(x or "")


def _wert(x):
    try:
        if isinstance(x, str):
            x = float(x.replace(".", "").replace(",", ".")) if "," in x else float(x)
        return float(x)
    except (TypeError, ValueError):
        return 0.0


class Blatt:
    def __init__(self, kopf, hochformat=False):
        self.W, self.H = (HOEHE, BREITE) if hochformat else (BREITE, HOEHE)
        self.seiten, self.b, self.kopf = [], [], kopf
        self.bilder = []   # je Seite: JPEG-Bytes eines Fotos oder None
        self.y = 0
        self.neue_seite()

    def t(self, x, y, groesse, text, fett=False, farbe=DUNKEL, rechts=False):
        if rechts:
            x -= _breite(text, groesse, fett)
        self.b.append(f"{farbe} rg BT /{'F2' if fett else 'F1'} {groesse} Tf {x:.1f} {y:.1f} Td ({_esc(text)}) Tj ET")

    def linie(self, x1, y1, x2, y2, farbe=GRAU, dicke=0.4):
        self.b.append(f"{farbe} RG {dicke} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def flaeche(self, x, y, b, h, farbe="0.95 0.95 0.93"):
        self.b.append(f"{farbe} rg {x:.1f} {y:.1f} {b:.1f} {h:.1f} re f")

    def neue_seite(self):
        if self.b:
            self.fuss()
            self.seiten.append(self.b)
            self.bilder.append(None)
        self.b = []
        titel, unter = self.kopf
        self.t(RAND, self.H - RAND - 6, 15, titel, fett=True)
        self.t(RAND, self.H - RAND - 19, 8.5, unter, farbe=GRAU)
        self.linie(RAND, self.H - RAND - 25, self.W - RAND, self.H - RAND - 25, AKZENT, 1)
        self.y = self.H - RAND - 42

    def fuss(self):
        self.t(self.W - RAND, 8 * MM, 7, f"Seite {len(self.seiten) + 1} · erstellt {date.today().strftime('%d.%m.%Y')}",
               farbe=GRAU, rechts=True)

    def platz(self, hoehe):
        if self.y - hoehe < 16 * MM:
            self.neue_seite()

    def ueberschrift(self, text, unter=""):
        self.platz(70)
        if self.y < self.H - RAND - 50:
            self.y -= 8
        self.t(RAND, self.y, 12, text, fett=True, farbe=AKZENT)
        if unter:
            self.t(RAND + _breite(text, 12, True) + 10, self.y, 8, unter, farbe=GRAU)
        self.y -= 16

    def absatz(self, text, groesse=8.5, farbe=DUNKEL):
        for z in _umbrechen(text, groesse, self.W - 2 * RAND):
            self.platz(12)
            self.t(RAND, self.y, groesse, z, farbe=farbe)
            self.y -= groesse + 3.5
        self.y -= 3

    def tabelle(self, spalten, zeilen, summe=None):
        """spalten: [(Titel, Breite in mm, rechtsbündig)]; zeilen: Listen mit Text; summe: Zeile (fett)."""
        def kopfzeile():
            self.flaeche(RAND, self.y - 4, sum(s[1] for s in spalten) * MM, 14)
            x = RAND
            for titel, b, rechts in spalten:
                self.t(x + (b * MM - 3 if rechts else 3), self.y, 7.5, titel, fett=True, rechts=rechts)
                x += b * MM
            self.y -= 15
        self.platz(40)
        kopfzeile()
        for i, z in enumerate((zeilen or [["– noch keine Einträge –"] + [""] * (len(spalten) - 1)]) + ([summe] if summe else [])):
            fett = summe is not None and i == len(zeilen)
            texte = [_umbrechen(str(w), 8, b * MM - 6, fett)[:3] for w, (_, b, _r) in zip(z, spalten)]
            hoehe = max(len(t) for t in texte) * 10 + 3
            if self.y - hoehe < 16 * MM:
                self.neue_seite()
                kopfzeile()
            x = RAND
            for t_, (_, b, rechts) in zip(texte, spalten):
                for k, zeile in enumerate(t_):
                    self.t(x + (b * MM - 3 if rechts else 3), self.y - k * 10, 8, zeile, fett=fett, rechts=rechts)
                x += b * MM
            self.y -= hoehe
            self.linie(RAND, self.y + 7, RAND + sum(s[1] for s in spalten) * MM, self.y + 7, "0.85 0.85 0.85", 0.3)
        self.y -= 8

    def bild_seite(self, jpeg, unterschrift=""):
        """Ganze Seite mit einem Foto (z. B. Beleg), oben eine Zeile dazu."""
        from brief_pdf import _jpeg_groesse
        b_px, h_px = _jpeg_groesse(jpeg)
        if not (b_px and h_px):
            return
        if self.b:
            self.fuss()
            self.seiten.append(self.b)
            self.bilder.append(None)
        self.b = []
        oben = self.H - RAND - (16 if unterschrift else 0)
        if unterschrift:
            self.t(RAND, self.H - RAND - 6, 9, unterschrift[:120], fett=True)
        frei_b, frei_h = self.W - 2 * RAND, oben - 14 * MM
        f = min(frei_b / b_px, frei_h / h_px)
        w, h = b_px * f, h_px * f
        self.b.append(f"q {w:.1f} 0 0 {h:.1f} {(self.W - w) / 2:.1f} {oben - h:.1f} cm /Bild Do Q")
        self.fuss()
        self.seiten.append(self.b)
        self.bilder.append(jpeg)
        self.b = []   # nach Fotoseiten nur noch weitere Fotos oder speichern()

    def speichern(self, pfad):
        if self.b:
            self.fuss()
            self.seiten.append(self.b)
            self.bilder.append(None)
        objekte = []

        def obj(inhalt):
            objekte.append(inhalt)
            return len(objekte)
        f1 = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        from brief_pdf import _jpeg_groesse
        seiten_id = len(objekte) + 1 + 2 * len(self.seiten) + sum(1 for x in self.bilder if x)
        kinder = []
        for bf, jpeg in zip(self.seiten, self.bilder):
            bild = ""
            if jpeg:
                b_px, h_px = _jpeg_groesse(jpeg)
                nr = obj(f"<< /Type /XObject /Subtype /Image /Width {b_px} /Height {h_px} /ColorSpace /DeviceRGB /BitsPerComponent 8 "
                         f"/Filter /DCTDecode /Length {len(jpeg)} >>\nstream\n".encode() + jpeg + b"\nendstream")
                bild = f" /XObject << /Bild {nr} 0 R >>"
            daten = zlib.compress("\n".join(bf).encode("cp1252", "replace"))
            inhalt = obj(f"<< /Length {len(daten)} /Filter /FlateDecode >>\nstream\n".encode() + daten + b"\nendstream")
            kinder.append(obj((f"<< /Type /Page /Parent {seiten_id} 0 R /MediaBox [0 0 {self.W:.2f} {self.H:.2f}] /Contents {inhalt} 0 R "
                               f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >>{bild} >> >>").encode()))
        obj(f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kinder)}] /Count {len(kinder)} >>".encode())
        katalog = obj(f"<< /Type /Catalog /Pages {seiten_id} 0 R >>".encode())
        aus = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        lagen = []
        for i, o in enumerate(objekte, 1):
            lagen.append(len(aus))
            aus += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
        xref = len(aus)
        aus += f"xref\n0 {len(objekte) + 1}\n0000000000 65535 f \n".encode()
        aus += b"".join(f"{l:010d} 00000 n \n".encode() for l in lagen)
        aus += f"trailer\n<< /Size {len(objekte) + 1} /Root {katalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        with open(pfad, "wb") as f:
            f.write(bytes(aus))


def erstellen(pfad, z, belege, schluessel, hh_typen, frist=""):
    zeitraum = f"{_de(z['von'])} – {_de(z['bis'])}"
    p = Blatt((f"Nebenkosten {z.get('objekt', '')}",
               f"Eigentümer {z.get('eigentuemer', '')} · Liegenschafts-Nr. {z.get('liegenschaft', '')} · Abrechnungszeitraum {zeitraum}"
               + (f" · Abrechnung an Mieter spätestens bis {_de(frist)}" if frist else "")))
    titel = lambda x: (belege.get(x.get("beleg")) or {}).get("titel") or x.get("beleg_titel") or ""  # noqa: E731

    p.ueberschrift("1. Heizkostenaufstellung", "Brennstoff Erdgas – Bezüge im Abrechnungszeitraum")
    br = z.get("brennstoff") or []
    p.tabelle([("Datum", 28, False), ("Erdgas kWh", 40, True), ("Bruttobetrag EUR", 40, True), ("Beleg / Hinweis", 160, False)],
              [[_de(x.get("datum")), _zahl(x.get("kwh"), 0), _zahl(x.get("brutto")), " – ".join(t for t in [titel(x), x.get("hinweis")] if t)] for x in br],
              ["Summe", _zahl(sum(_wert(x.get("kwh")) for x in br), 0), _zahl(sum(_wert(x.get("brutto")) for x in br)), ""] if br else None)
    a = z.get("abgaben") or {}
    p.tabelle([("Abgaben (in den Brennstoffkosten enthalten)", 90, False), ("Betrag EUR", 40, True)],
              [["CO2-Steuer", _zahl(a.get("co2"))], ["Energiesteuer", _zahl(a.get("energiesteuer"))],
               ["Netzentgelt", _zahl(a.get("netzentgelt"))], ["Weitere Abgaben", _zahl(a.get("weitere"))]])
    hn = z.get("heizneben") or []
    p.ueberschrift("Heiznebenkosten")
    p.tabelle([("Kostenart", 70, False), ("Datum", 24, False), ("Brutto EUR", 30, True), ("MW %", 16, True),
               ("haushalt.DL EUR", 30, True), ("HH-Typ", 16, True), ("Beleg / Hinweis", 82, False)],
              [[x.get("art"), _de(x.get("datum")), _zahl(x.get("brutto")), _zahl(x.get("mwst"), 0), _zahl(x.get("hhdl")) if x.get("hhdl") not in ("", None) else "",
                x.get("hhtyp") or "", " – ".join(t for t in [titel(x), x.get("hinweis")] if t)] for x in hn],
              ["Summe", "", _zahl(sum(_wert(x.get("brutto")) for x in hn)), "", "", "", ""] if hn else None)

    p.neue_seite()
    p.ueberschrift("2. Betriebskostenaufstellung", "nur umlagefähige Kosten, brutto")
    bk = z.get("betrieb") or []
    p.tabelle([("Kostenart", 62, False), ("BS", 14, False), ("Datum", 24, False), ("Brutto EUR", 28, True), ("MW %", 14, True),
               ("haushalt.DL EUR", 28, True), ("HH-Typ", 14, True), ("Beleg / Hinweis", 84, False)],
              [[x.get("art"), x.get("bs") or "", _de(x.get("datum")), _zahl(x.get("brutto")), _zahl(x.get("mwst"), 0),
                _zahl(x.get("hhdl")) if x.get("hhdl") not in ("", None) else "", x.get("hhtyp") or "",
                " – ".join(t for t in [titel(x), x.get("hinweis")] if t)] for x in bk],
              ["Summe", "", "", _zahl(sum(_wert(x.get("brutto")) for x in bk)), "", "", "", ""] if bk else None)
    p.absatz(f"Gesamtmenge geliefertes Wasser laut Wasserversorger: {_zahl(z.get('wasser_cbm')) or '–'} m³")
    p.absatz("Verteilerschlüssel: " + " · ".join(f"{k} {v}" for k, v in schluessel.items())
             + ".  HH-Typ: " + " · ".join(f"{k} {v}" for k, v in hh_typen.items()), 7.5, GRAU)

    p.ueberschrift("3. Nutzerliste")
    p.tabelle([("Nutzer-Nr.", 22, False), ("Lage", 14, False), ("Nutzer / Name", 58, False), ("Einzug", 22, False), ("Auszug", 22, False),
               ("S030 HZ m²", 24, True), ("S031 WW m²", 24, True), ("S015 Pers.", 20, True), ("VZ Heizung EUR", 30, True), ("VZ Nebenk. EUR", 30, True)],
              [[e.get("nr"), e.get("lage"), " – ".join(t for t in [e.get("nutzer"), e.get("nutzung")] if t) or "Leerstand", _de(e.get("einzug")),
                _de(e.get("auszug")), _zahl(e.get("hz_flaeche")), _zahl(e.get("ww_flaeche")), _zahl(e.get("personen"), 0),
                _zahl(e.get("vz_heizung")), _zahl(e.get("vz_neben"))] for e in z.get("einheiten") or []])

    zs = z.get("zaehler") or []
    if zs:
        p.ueberschrift("4. Zählerstände")
        zeilen = []
        for m in zs:
            for s in m.get("staende") or [{}]:
                zeilen.append([m.get("name"), m.get("art"), m.get("nummer"), _de(s.get("datum")), _zahl(s.get("stand"), 3),
                               m.get("einheit"), ("Stichtagswert. " if s.get("stichtag") else "") + (s.get("hinweis") or "")])
        p.tabelle([("Zähler", 55, False), ("Art", 30, False), ("Nummer", 38, False), ("Datum", 24, False), ("Stand", 30, True),
                   ("Einheit", 18, False), ("Hinweis", 74, False)], zeilen)
    if z.get("hinweise") or z.get("notiz"):
        p.ueberschrift("Hinweise")
        for h in z.get("hinweise") or []:
            p.absatz("• " + h)
        if z.get("notiz"):
            p.absatz("Notiz: " + z["notiz"])
    p.speichern(pfad)
