#!/usr/bin/env python3
"""Garten-Fragen und Foto-Check mit Claude (Aufruf aus script.garten_ki).

Argument 1: Base64 des JSON {art: "foto"|"frage", frage, pflanze, beet, bereich, wetter, plan,
            datei (Foto-Pfad, z. B. von Telegram), plan_laden (Plan aus garten_daten.json lesen), merken (Ergebnis in den Foto-Verlauf)}.
Argument 2 ff. (optional): das Foto als Base64-JPEG, in Stücke geteilt.
Der API-Schlüssel kommt aus der Anthropic-Integration von Home Assistant (.storage), nicht aus dem Repository.
Ausgabe immer JSON: {"ok": true, "text": "..."} oder {"ok": false, "fehler": "..."}.
"""
import base64
import io
import json
import os
import sys
from datetime import datetime

DATEN = "/config/www/garten_daten.json"

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
    beete = {b["id"]: b.get("name", "") for b in d.get("beete", [])}
    return "; ".join(f"{beete.get(p.get('beet'), '')}: {p.get('pflanze', '')} {p.get('anzahl', '')}×"
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
    if not isinstance(d, dict) or not isinstance(d.get("beete"), list):
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
    kontext.append(f"Datum: {auftrag.get('datum', '')}")
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
        system=SYSTEM,
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
    if auftrag.get("merken"):
        merken(auftrag, ergebnis, bild)
    print(json.dumps({"ok": True, "text": ergebnis}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": f"{type(fehler).__name__}: {fehler}"[:300]}, ensure_ascii=False))
