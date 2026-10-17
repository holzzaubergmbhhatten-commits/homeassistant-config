"""Einfacher Brief als PDF (DIN 5008, Helvetica, ohne Zusatzbibliotheken) – für Schreiben aus der digitalen Akte."""
import zlib

# Zeichenbreiten Helvetica (1/1000 em) für die gängigen Zeichen, Rest ~556
_BREITE = {" ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191, "(": 333, ")": 333, "*": 389,
           "+": 584, ",": 278, "-": 333, ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584, "?": 556,
           "@": 1015, "[": 278, "\\": 278, "]": 278, "_": 556, "|": 260, "€": 556, "–": 556, "„": 333, "“": 333, "”": 333,
           "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778, "H": 722, "I": 278, "J": 500, "K": 667,
           "L": 556, "M": 833, "N": 722, "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722, "V": 667,
           "W": 944, "X": 667, "Y": 667, "Z": 611, "Ä": 667, "Ö": 778, "Ü": 722,
           "f": 278, "i": 222, "j": 222, "l": 222, "m": 833, "r": 333, "t": 278, "w": 722, "c": 500, "k": 500, "s": 500,
           "v": 500, "x": 500, "y": 500, "z": 500, "ß": 611}


def _breite(text, groesse):
    return sum(_BREITE.get(z, 556) for z in text) * groesse / 1000


def _umbrechen(text, groesse, max_breite):
    zeilen = []
    for absatz in text.split("\n"):
        aktuell = ""
        for wort in absatz.split(" "):
            versuch = (aktuell + " " + wort).strip()
            if _breite(versuch, groesse) <= max_breite or not aktuell:
                aktuell = versuch
            else:
                zeilen.append(aktuell)
                aktuell = wort
        zeilen.append(aktuell)
    return zeilen


def _esc(t):
    return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def brief(pfad, absender, empfaenger, ort_datum, betreff, text, gruss="Mit freundlichen Grüßen", name=""):
    """absender/empfaenger: Listen von Zeilen. Schreibt eine A4-PDF (eine oder mehrere Seiten)."""
    mm = 72 / 25.4
    links, breite = 25 * mm, 165 * mm
    befehle_seiten = []
    b = []

    def t(x, y, groesse, zeile, fett=False):
        b.append(f"BT /{'F2' if fett else 'F1'} {groesse} Tf {x:.1f} {y:.1f} Td ({_esc(zeile)}) Tj ET")

    hoehe = 297 * mm
    # Absenderzeile über dem Anschriftfeld (klein) und Absender rechts oben
    t(links, hoehe - 50 * mm, 7, " · ".join(absender)[:110])
    y = hoehe - 20 * mm
    for z in absender:
        t(125 * mm, y, 9, z)
        y -= 11
    # Anschriftfeld
    y = hoehe - 60 * mm
    for z in empfaenger:
        t(links, y, 11, z)
        y -= 14
    t(125 * mm, hoehe - 95 * mm, 11, ort_datum)
    y = hoehe - 110 * mm
    for z in _umbrechen(betreff, 11, breite):
        t(links, y, 11, z, fett=True)
        y -= 15
    y -= 12
    zeilen = _umbrechen(text, 11, breite) + ["", gruss, "", "", name]
    for z in zeilen:
        if y < 25 * mm:
            befehle_seiten.append(b)
            b = []
            y = hoehe - 25 * mm
        if z:
            t(links, y, 11, z)
        y -= 15
    befehle_seiten.append(b)

    # PDF zusammenbauen
    objekte = []
    def obj(inhalt):
        objekte.append(inhalt)
        return len(objekte)
    font1 = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font2 = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    seiten_id = len(objekte) + 1 + 2 * len(befehle_seiten)
    kinder = []
    for bf in befehle_seiten:
        daten = zlib.compress("\n".join(bf).encode("cp1252", "replace"))
        inhalt = obj(f"<< /Length {len(daten)} /Filter /FlateDecode >>\nstream\n".encode() + daten + b"\nendstream")
        kinder.append(obj(f"<< /Type /Page /Parent {seiten_id} 0 R /MediaBox [0 0 595.28 841.89] /Contents {inhalt} 0 R "
                          f"/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> >>".encode()))
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
