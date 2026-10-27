"""Mehrere PDFs zu einer zusammenhängen (z. B. Schreiben + Belege als Anlagen).

Nimmt pypdf, wenn es installiert ist (kann jede PDF). Sonst ein kleiner eigener Weg, der die PDFs versteht, die unsere
eigenen Programme schreiben (brief_pdf, nk_pdf, Fotos→PDF über Pillow): Objekte einlesen, Nummern verschieben,
eine gemeinsame Seitenliste bauen."""
import re


def verbinden(ziel, pfade):
    try:
        from pypdf import PdfWriter
    except ImportError:
        PdfWriter = None
    if PdfWriter is not None:
        w = PdfWriter()
        for p in pfade:
            w.append(p)
        with open(ziel, "wb") as f:
            w.write(f)
        return
    teile = []
    for p in pfade:
        with open(p, "rb") as f:
            teile.append(_objekte(f.read()))
    _schreiben(ziel, teile)


def _objekte(roh):
    """{Nummer: (Wörterbuch-Bytes, Stream-Bytes oder None)} aus einer PDF mit klassischer xref-Tabelle."""
    start = int(re.findall(rb"startxref\s+(\d+)", roh)[-1])
    m = re.match(rb"xref\s+(\d+)\s+(\d+)\s+", roh[start:])
    if not m:
        raise ValueError("PDF ohne klassische xref-Tabelle – bitte pypdf installieren")
    erste, anzahl = int(m.group(1)), int(m.group(2))
    pos = start + m.end()
    objekte = {}
    for k in range(anzahl):
        zeile = roh[pos + 20 * k: pos + 20 * k + 20]
        if zeile[17:18] != b"n":
            continue
        lage = int(zeile[:10])
        kopf = re.match(rb"(\d+)\s+0\s+obj\s*", roh[lage:])
        a = lage + kopf.end()
        s = roh.find(b"stream", a)
        e = roh.find(b"endobj", a)
        if 0 <= s < e and roh[a:s].rstrip().endswith(b">>"):
            woerterbuch = roh[a:s].rstrip()
            laenge = int(re.search(rb"/Length\s+(\d+)", woerterbuch).group(1))
            d = s + len(b"stream")
            d += 2 if roh[d:d + 2] == b"\r\n" else 1
            objekte[erste + k] = (woerterbuch, roh[d:d + laenge])
        else:
            objekte[erste + k] = (roh[a:e].rstrip(), None)
    return objekte


def _seiten(objekte):
    """Seitennummern in Lesereihenfolge (über die Kids der Seitenbäume)."""
    wurzel = next(n for n, (w, _) in objekte.items() if re.search(rb"/Type\s*/Catalog", w))
    pages = int(re.search(rb"/Pages\s+(\d+)\s+0\s+R", objekte[wurzel][0]).group(1))

    def sammeln(n):
        w = objekte[n][0]
        if re.search(rb"/Type\s*/Pages", w):
            kids = re.search(rb"/Kids\s*\[([^\]]*)\]", w).group(1)
            return [s for k in re.findall(rb"(\d+)\s+0\s+R", kids) for s in sammeln(int(k))]
        return [n]
    return sammeln(pages)


def _schreiben(ziel, teile):
    neu, alle_seiten = [], []
    for objekte in teile:
        seiten = _seiten(objekte)
        weg = {n for n, (w, _) in objekte.items() if re.search(rb"/Type\s*/(Catalog|Pages)\b", w)}
        nummer = {n: len(neu) + i + 1 for i, n in enumerate(n for n in sorted(objekte) if n not in weg)}   # lückenlos neu zählen
        for n in sorted(nummer):
            w, s = objekte[n]
            w = re.sub(rb"(\d+)\s+0\s+R", lambda m: b"%d 0 R" % nummer.get(int(m.group(1)), 0), w)
            neu.append((nummer[n], w, s, n in seiten))
        alle_seiten += [nummer[s] for s in seiten]
    pages_nr, katalog_nr = len(neu) + 1, len(neu) + 2
    aus = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    lagen = []
    for n, w, s, ist_seite in neu:
        if ist_seite:
            w = re.sub(rb"/Parent\s+\d+\s+0\s+R", b"/Parent %d 0 R" % pages_nr, w)
        lagen.append(len(aus))
        aus += b"%d 0 obj\n" % n + w + ((b"\nstream\n" + s + b"\nendstream") if s is not None else b"") + b"\nendobj\n"
    lagen.append(len(aus))
    aus += b"%d 0 obj\n<< /Type /Pages /Kids [%s] /Count %d >>\nendobj\n" % (
        pages_nr, b" ".join(b"%d 0 R" % s for s in alle_seiten), len(alle_seiten))
    lagen.append(len(aus))
    aus += b"%d 0 obj\n<< /Type /Catalog /Pages %d 0 R >>\nendobj\n" % (katalog_nr, pages_nr)
    xref = len(aus)
    aus += b"xref\n0 %d\n0000000000 65535 f \n" % (katalog_nr + 1)
    aus += b"".join(b"%010d 00000 n \n" % l for l in lagen)
    aus += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (katalog_nr + 1, katalog_nr, xref)
    with open(ziel, "wb") as f:
        f.write(bytes(aus))
