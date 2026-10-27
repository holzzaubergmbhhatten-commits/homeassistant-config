"""Brief als Word-Datei (.docx) ohne Zusatzbibliotheken – gleicher Aufbau wie brief_pdf, aber zum Weiterbearbeiten
(Empfänger, Aktenzeichen, Beträge ergänzen). Kopf mit Name und Anschrift (Wappen rechts), Rücksendeangabe, Anschrift links
und Infoblock rechts, Betreff fett, Text, Gruß, Name; Fußzeile mit den Kontaktdaten."""
import zipfile
from xml.sax.saxutils import escape

from brief_pdf import _jpeg_groesse

_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
       'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
GRAU, AKZENT = "6B7078", "406B3B"


def _lauf(text, groesse=11, fett=False, farbe=None):
    eig = f'<w:sz w:val="{int(groesse * 2)}"/>' + ("<w:b/>" if fett else "") + (f'<w:color w:val="{farbe}"/>' if farbe else "")
    return f'<w:r><w:rPr>{eig}</w:rPr><w:t xml:space="preserve">{escape(str(text))}</w:t></w:r>'


def _absatz(inhalt="", nach=0, rechts=False, linie=False):
    eig = f'<w:spacing w:before="0" w:after="{nach}" w:line="264" w:lineRule="auto"/>'
    if rechts:
        eig += '<w:jc w:val="right"/>'
    if linie:
        eig += f'<w:pBdr><w:bottom w:val="single" w:sz="10" w:space="4" w:color="{AKZENT}"/></w:pBdr>'
    return f"<w:p><w:pPr>{eig}</w:pPr>{inhalt}</w:p>"


def _zelle(breite, absaetze):
    return (f'<w:tc><w:tcPr><w:tcW w:w="{breite}" w:type="dxa"/></w:tcPr>{"".join(absaetze) or _absatz()}</w:tc>')


def _tabelle(zellen):
    gitter = "".join(f'<w:gridCol w:w="{b}"/>' for b, _ in zellen)
    return ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders><w:top w:val="nil"/><w:left w:val="nil"/>'
            '<w:bottom w:val="nil"/><w:right w:val="nil"/><w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders>'
            '<w:tblLayout w:type="fixed"/></w:tblPr>'
            f'<w:tblGrid>{gitter}</w:tblGrid><w:tr>{"".join(_zelle(b, a) for b, a in zellen)}</w:tr></w:tbl>')


def _bild(breite_cm, hoehe_cm):
    cx, cy = int(breite_cm * 360000), int(hoehe_cm * 360000)
    return (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            '<wp:docPr id="1" name="Wappen"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="wappen.jpg"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="rIdWappen"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            '</pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')


def brief(pfad, absender, empfaenger, ort_datum, betreff, text, gruss="Mit freundlichen Grüßen", name="",
          info=None, fuss=None, wappen=None):
    """Gleiche Parameter wie brief_pdf.brief (absender[0] = Name, info = [(Bezeichnung, Wert)], wappen = JPEG-Bytes)."""
    absender = [z for z in absender or [] if z]
    w_b, w_h = _jpeg_groesse(wappen) if wappen else (0, 0)
    kopf_rechts = []
    if w_b and w_h:
        h = 2.4
        b = min(4.0, h * w_b / w_h)
        kopf_rechts = [_absatz(_bild(b, b * w_h / w_b), rechts=True)]
    kopf_links = [_absatz(_lauf(absender[0] if absender else "", 17, fett=True)),
                  _absatz(_lauf(" · ".join(absender[1:]), 9, farbe=GRAU))]
    teile = [_tabelle([(6800, kopf_links), (2800, kopf_rechts)]), _absatz(linie=True, nach=600)]

    links = [_absatz(_lauf(" · ".join(absender[:3]), 7, farbe=GRAU), nach=120)]
    links += [_absatz(_lauf(z, 11)) for z in empfaenger or [] if z]
    rechts = []
    for bez, wert in (info or []) + [("Datum", ort_datum.split(", ")[-1])]:
        if wert:
            rechts += [_absatz(_lauf(bez, 7.5, farbe=GRAU)), _absatz(_lauf(wert, 9.5), nach=80)]
    teile += [_tabelle([(5600, links), (4000, rechts)]), _absatz(nach=480)]

    teile.append(_absatz(_lauf(betreff, 12, fett=True), nach=360))
    for zeile in str(text or "").split("\n"):
        teile.append(_absatz(_lauf(zeile, 11) if zeile.strip() else "", nach=0))
    teile += [_absatz(), _absatz(_lauf(gruss, 11)), _absatz(), _absatz(), _absatz(_lauf(name, 11, fett=True) if name else "")]

    fusszeilen = [z for z in (fuss or [" · ".join(absender)]) if z][:2]
    fuss_xml = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {_NS}>'
                + "".join(_absatz(_lauf(z, 7.5, farbe=GRAU)) for z in fusszeilen) + "</w:ftr>")
    sekt = ('<w:sectPr><w:footerReference w:type="default" r:id="rIdFuss"/><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1000" w:right="1134" w:bottom="1300" w:left="1418" w:header="500" w:footer="500" w:gutter="0"/></w:sectPr>')
    dokument = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_NS}><w:body>'
                + "".join(teile) + sekt + "</w:body></w:document>")
    stile = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr>'
             '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="22"/><w:lang w:val="de-DE"/></w:rPr></w:rPrDefault>'
             '</w:docDefaults></w:styles>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdStile" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rIdFuss" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
            + ('<Relationship Id="rIdWappen" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
               'Target="media/wappen.jpg"/>' if w_b and w_h else "") + "</Relationships>")
    typen = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/><Default Extension="jpg" ContentType="image/jpeg"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
             '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
             '</Types>')
    paket = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
             'Target="word/document.xml"/></Relationships>')
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", typen)
        z.writestr("_rels/.rels", paket)
        z.writestr("word/document.xml", dokument)
        z.writestr("word/styles.xml", stile)
        z.writestr("word/footer1.xml", fuss_xml)
        z.writestr("word/_rels/document.xml.rels", rels)
        if w_b and w_h:
            z.writestr("word/media/wappen.jpg", wappen)
