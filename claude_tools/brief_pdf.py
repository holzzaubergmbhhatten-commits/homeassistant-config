"""Brief als PDF (DIN 5008, Form B) ohne Zusatzbibliotheken – für Schreiben aus der digitalen Akte.

Aufbau: Kopf mit Name des Absenders und feiner Linie, Rücksendeangabe über dem Anschriftfeld, rechts der Informationsblock
(Ihr Zeichen/Vertragsnummer, Ihr Schreiben vom, Telefon, Datum), Betreff fett, Brieftext, Gruß, Unterschriftsname und
eine Fußzeile mit den Kontaktdaten. Schrift Helvetica (WinAnsi, Umlaute und € gehen)."""
import zlib

_BREITE = {" ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191, "(": 333, ")": 333, "*": 389,
           "+": 584, ",": 278, "-": 333, ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584, "?": 556,
           "@": 1015, "[": 278, "\\": 278, "]": 278, "_": 556, "|": 260, "€": 556, "–": 556, "„": 333, "“": 333, "”": 333,
           "·": 278, "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778, "H": 722, "I": 278, "J": 500,
           "K": 667, "L": 556, "M": 833, "N": 722, "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
           "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611, "Ä": 667, "Ö": 778, "Ü": 722, "f": 278, "i": 222, "j": 222,
           "l": 222, "m": 833, "r": 333, "t": 278, "w": 722, "c": 500, "k": 500, "s": 500, "v": 500, "x": 500, "y": 500,
           "z": 500, "ß": 611}
GRAU = "0.42 0.44 0.47"
DUNKEL = "0.13 0.15 0.18"
AKZENT = "0.25 0.42 0.23"   # ruhiges Grün


def _breite(text, groesse, fett=False):
    return sum(_BREITE.get(z, 556) for z in text) * groesse / 1000 * (1.06 if fett else 1)


def _umbrechen(text, groesse, max_breite, fett=False):
    zeilen = []
    for absatz in str(text).split("\n"):
        aktuell = ""
        for wort in absatz.split(" "):
            versuch = (aktuell + " " + wort).strip()
            if _breite(versuch, groesse, fett) <= max_breite or not aktuell:
                aktuell = versuch
            else:
                zeilen.append(aktuell)
                aktuell = wort
        zeilen.append(aktuell)
    return zeilen


def _esc(t):
    return str(t).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def brief(pfad, absender, empfaenger, ort_datum, betreff, text, gruss="Mit freundlichen Grüßen", name="",
          info=None, fuss=None):
    """absender/empfaenger: Zeilenlisten (absender[0] = Name). info: [(Bezeichnung, Wert)] für den Infoblock rechts.
    fuss: Zeilen für die Fußzeile (sonst aus dem Absender)."""
    mm = 72 / 25.4
    hoehe = 297 * mm
    links, rechts_x, breite = 25 * mm, 125 * mm, 165 * mm
    seiten, b = [], []

    def t(x, y, groesse, zeile, fett=False, farbe=DUNKEL, rechtsbuendig=False):
        if rechtsbuendig:
            x -= _breite(zeile, groesse, fett)
        b.append(f"{farbe} rg BT /{'F2' if fett else 'F1'} {groesse} Tf {x:.1f} {y:.1f} Td ({_esc(zeile)}) Tj ET")

    def linie(x1, y1, x2, y2, farbe=AKZENT, dicke=0.8):
        b.append(f"{farbe} RG {dicke} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def fusszeile(nr):
        zeilen = fuss or [" · ".join(z for z in absender if z)]
        linie(links, 18 * mm, links + breite, 18 * mm, GRAU, 0.4)
        y = 14 * mm
        for z in zeilen[:2]:
            t(links, y, 7.5, z, farbe=GRAU)
            y -= 9.5
        t(links + breite, 14 * mm, 7.5, f"Seite {nr}", farbe=GRAU, rechtsbuendig=True)

    # Kopf: Name groß, darunter Anschrift, feine Akzentlinie
    t(links, hoehe - 22 * mm, 17, absender[0] if absender else "", fett=True)
    t(links, hoehe - 28 * mm, 9, " · ".join(z for z in absender[1:] if z), farbe=GRAU)
    linie(links, hoehe - 32 * mm, links + breite, hoehe - 32 * mm, AKZENT, 1.2)
    # Rücksendeangabe und Anschriftfeld (Form B: 45 mm von oben)
    t(links, hoehe - 50 * mm, 7, " · ".join(z for z in absender[:3] if z), farbe=GRAU)
    linie(links, hoehe - 51.5 * mm, links + 85 * mm, hoehe - 51.5 * mm, GRAU, 0.3)
    y = hoehe - 57 * mm
    for z in [z for z in empfaenger if z][:6]:
        t(links, y, 11, z)
        y -= 14
    # Informationsblock rechts
    y = hoehe - 50 * mm
    for bez, wert in (info or []) + [("Datum", ort_datum.split(", ")[-1])]:
        if not wert:
            continue
        t(rechts_x, y, 7.5, bez, farbe=GRAU)
        y -= 10
        for z in _umbrechen(wert, 9.5, 60 * mm)[:2]:
            t(rechts_x, y, 9.5, z)
            y -= 12
        y -= 4
    # Betreff und Text
    y = min(y, hoehe - 103 * mm) - 6
    for z in _umbrechen(betreff, 12, breite, fett=True):
        t(links, y, 12, z, fett=True)
        y -= 16
    y -= 14
    zeilen = _umbrechen(text, 11, breite) + ["", gruss, "", "", ""]
    nr = 1
    for z in zeilen:
        if y < 30 * mm:
            fusszeile(nr)
            seiten.append(b)
            b, nr = [], nr + 1
            y = hoehe - 25 * mm
        if z:
            t(links, y, 11, z)
        y -= 15.5
    if name:
        t(links, y + 15.5, 11, name, fett=True)
    fusszeile(nr)
    seiten.append(b)

    objekte = []

    def obj(inhalt):
        objekte.append(inhalt)
        return len(objekte)
    f1 = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    seiten_id = len(objekte) + 1 + 2 * len(seiten)
    kinder = []
    for bf in seiten:
        daten = zlib.compress("\n".join(bf).encode("cp1252", "replace"))
        inhalt = obj(f"<< /Length {len(daten)} /Filter /FlateDecode >>\nstream\n".encode() + daten + b"\nendstream")
        kinder.append(obj(f"<< /Type /Page /Parent {seiten_id} 0 R /MediaBox [0 0 595.28 841.89] /Contents {inhalt} 0 R "
                          f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> >>".encode()))
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
