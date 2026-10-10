#!/usr/bin/env python3
"""Garten-To-dos für das Start-Dashboard (Aufruf aus dem Template-Sensor "Garten Aufgaben").

Argument 1: Base64 des JSON {"tage": [Tagesvorhersage aus weather.get_forecasts], "jetzt": aktuelle Temperatur}.
Liest den Pflanzplan aus /config/www/garten_daten.json – die Garten-Seite legt dort unter "info" eine
Kurzfassung der Pflanzen und Beete ab (Monate für Vorziehen/Säen/Ernte usw.), damit hier nichts doppelt steht.
Ausgabe immer JSON: {"aufgaben": [{"icon", "farbe", "titel", "text"}], "bald": [...]}.
"""
import base64
import json
import sys
from datetime import date, timedelta

DATEN = "/config/www/garten_daten.json"
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]


def aufgabe(icon, farbe, titel, text=""):
    return {"icon": icon, "farbe": farbe, "titel": titel, "text": text}


def namen(liste):
    liste = sorted(set(liste))
    return ", ".join(liste[:-1]) + " und " + liste[-1] if len(liste) > 1 else (liste[0] if liste else "")


def main():
    wetter = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8")) if len(sys.argv) > 1 and sys.argv[1].strip() else {}
    try:
        with open(DATEN, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        print(json.dumps({"aufgaben": [], "bald": []}))
        return
    info = d.get("info") or {}
    pflanzen = info.get("pflanzen") or {}
    beete = info.get("beete") or {}
    heute = date.today()
    m, jahr = heute.month, heute.year
    plan_jahr = jahr + 1 if m >= 9 else jahr

    tage = [t for t in (wetter.get("tage") or []) if isinstance(t, dict)][:5]
    jetzt = wetter.get("jetzt")
    tmax = max([t.get("temperature", -99) or -99 for t in tage[:2]] + [jetzt if isinstance(jetzt, (int, float)) else -99])
    tmin = min([t.get("templow", 99) if t.get("templow") is not None else 99 for t in tage[:3]] or [99])
    regen_heute = (tage[0].get("precipitation") or 0) if tage else 0
    regen2 = sum((t.get("precipitation") or 0) for t in tage[:2])

    # Was steht gerade in den Beeten? (Plan dieses Jahres + "Was war drin?" dieses Jahres)
    aktiv = [(p.get("pflanze"), p.get("beet")) for p in d.get("pflanzungen", []) if p.get("saison") == jahr]
    aktiv += [(h.get("pflanze"), h.get("beet")) for h in d.get("historie", []) if h.get("saison") == jahr]
    aktiv = [(pid, bid) for pid, bid in aktiv if pid in pflanzen]
    # Was soll als Nächstes wachsen? (Plan fürs kommende Jahr + Auswahl unter "Pflanzen")
    geplant = {p.get("pflanze") for p in d.get("pflanzungen", []) if p.get("saison") == plan_jahr}
    geplant |= {pid for pid, n in (d.get("wunsch") or {}).items() if n}
    geplant = {pid for pid in geplant if pid in pflanzen}
    pf = lambda pid: pflanzen[pid]
    ist_gh = lambda bid: bool((beete.get(bid) or {}).get("gh")) or str(bid or "").startswith("gh-")

    aufgaben, bald = [], []

    # Frost – das Dach ist offen, dort wird es genauso kalt
    if tmin < 2:
        # nur, was noch im Beet steht (nach der letzten Erntezeit ist es meist abgeräumt)
        empf = [pf(pid)["name"] for pid, _ in aktiv if pf(pid).get("frost") and m <= max(pf(pid).get("ernte") or [12])]
        aufgaben.append(aufgabe("mdi:snowflake-alert", "#5AC8FA", f"Frost bis {round(tmin)} °C",
                                f"Abends mit Vlies abdecken: {namen(empf)}." if empf else "Frisch Gepflanztes abends mit Vlies abdecken."))

    # Gießen unter dem Dach (kein Regen) und draußen (nach Regen-Vorhersage)
    gh_beete = info.get("gh_beete") or any(b.get("gh") for b in beete.values())
    garten_beete = info.get("garten_beete") or any(not b.get("gh") for b in beete.values())
    wachstum = 4 <= m <= 10 or (m in (3, 11) and tmax >= 15)
    if gh_beete and wachstum:
        if tmax >= 28:
            aufgaben.append(aufgabe("mdi:watering-can", "#007AFF", "Unter dem Dach gießen", "Morgens ca. 20 Minuten Tropfschlauch, nachmittags nochmal 10 Minuten – dort kommt kein Regen an."))
        elif tmax >= 20:
            aufgaben.append(aufgabe("mdi:watering-can", "#007AFF", "Unter dem Dach gießen", "Morgens ca. 15 Minuten – dort kommt kein Regen an."))
        elif tmax >= 12 and heute.toordinal() % 2 == 0:
            aufgaben.append(aufgabe("mdi:watering-can", "#007AFF", "Unter dem Dach gießen", "Heute ca. 10–15 Minuten (alle 2 Tage reicht)."))
    if garten_beete and wachstum:
        if regen_heute >= 2 or regen2 >= 5:
            aufgaben.append(aufgabe("mdi:weather-pouring", "#8E8E93", "Draußen nicht gießen",
                                    f"Es kommen ca. {round(regen2)} mm Regen{' – heute regnet es' if regen_heute >= 2 else ''}."))
        elif tmax >= 25:
            aufgaben.append(aufgabe("mdi:watering-can", "#007AFF", "Erdhaufen kräftig gießen", "Früh morgens 15–20 l pro Meter, danach mulchen."))
        elif tmax >= 18 and heute.toordinal() % 3 == 0:
            aufgaben.append(aufgabe("mdi:watering-can", "#007AFF", "Erdhaufen gießen, wenn trocken", "Ca. 10 l pro Meter – Fingerprobe: 3 cm tief trocken?"))
    if tmax >= 30 and gh_beete:
        aufgaben.append(aufgabe("mdi:white-balance-sunny", "#FF9500", "Hitze unter der Folie", "Morgens gründlich gießen und die Erde mulchen."))

    # Kartoffeln: vorkeimen (ca. 4 Wochen vor dem Legen), legen, anhäufeln
    kart_aktiv = any(pid == "kartoffel" for pid, _ in aktiv)
    kart_geplant = "kartoffel" in geplant or kart_aktiv
    if kart_geplant:
        if (m == 3 and heute.day >= 10) or (m == 4 and heute.day <= 5):
            aufgaben.append(aufgabe("mdi:egg-outline", "#8E5B3A", "Kartoffeln vorkeimen",
                                    "Saatkartoffeln in Eierkartons, Augen nach oben, hell und kühl (10–15 °C) hinstellen – nach ca. 4 Wochen legen."))
        elif m == 3 and heute.day >= 1:
            bald.append(aufgabe("mdi:egg-outline", "#8E5B3A", "Ab 10. März: Kartoffeln vorkeimen"))
        elif m == 2 and heute.day >= 20:
            bald.append(aufgabe("mdi:cart-outline", "#8E5B3A", "Saatkartoffeln kaufen", "Zum Vorkeimen ab Mitte März."))
        if (m == 4 and heute.day >= 10) or (m == 5 and heute.day <= 10):
            if tmin >= 2:
                aufgaben.append(aufgabe("mdi:shovel", "#8E5B3A", "Kartoffeln legen", "Ca. 10 cm tief, 35 cm Abstand, Keime nach oben – in die Erdhaufen."))
            else:
                bald.append(aufgabe("mdi:shovel", "#8E5B3A", "Kartoffeln legen, sobald kein Frost mehr kommt"))
    if kart_aktiv and ((m == 5 and heute.day >= 10) or (m == 6 and heute.day <= 25)):
        aufgaben.append(aufgabe("mdi:image-filter-hdr", "#8E5B3A", "Kartoffeln anhäufeln",
                                "Wenn das Kraut 15–20 cm hoch ist: Erde von der Seite bis an die Blätter heranziehen, nach 2–3 Wochen nochmal."
                                + (" Am besten nach dem Regen – feuchte Erde hält besser." if regen2 >= 2 else "")))
    if kart_aktiv and m == 5 and tmin < 3:
        aufgaben.append(aufgabe("mdi:snowflake", "#5AC8FA", "Kartoffelkraut schützen", "Bei Spätfrost Erde über die Triebe häufeln oder Vlies drauf."))

    # Säen, vorziehen, Jungpflanzen kaufen (diesen und nächsten Monat)
    vorziehen, saeen, dach, kaufen, bald_saat = [], [], [], [], []
    naechster = m % 12 + 1
    for pid in geplant:
        p = pf(pid)
        if pid == "kartoffel":
            continue
        weg = p.get("weg", "")
        if m in p.get("vorziehen", []) and weg != "kaufen":
            vorziehen.append(p["name"])
        if m in p.get("draussen", []):
            (kaufen if weg == "kaufen" else saeen).append(p["name"])
        if m in p.get("ghm", []):
            (kaufen if weg == "kaufen" else dach).append(p["name"])
        if naechster in p.get("vorziehen", []) + p.get("draussen", []) + p.get("ghm", []) and m not in p.get("vorziehen", []) + p.get("draussen", []) + p.get("ghm", []):
            bald_saat.append(p["name"])
    if vorziehen:
        aufgaben.append(aufgabe("mdi:sprout", "#007AFF", "Auf der Fensterbank vorziehen", namen(vorziehen)))
    if saeen:
        aufgaben.append(aufgabe("mdi:seed", "#34A853", "Draußen säen/pflanzen", namen(saeen) + (" (nicht bei Frost)" if tmin < 2 else "")))
    if dach:
        aufgaben.append(aufgabe("mdi:seed", "#34A853", "Unters Dach säen/pflanzen", namen(dach)))
    if kaufen:
        aufgaben.append(aufgabe("mdi:cart-outline", "#FF9500", "Jungpflanzen kaufen und pflanzen", namen(kaufen)))
    if bald_saat:
        bald.append(aufgabe("mdi:calendar-arrow-right", "#34A853", f"Im {MONATE[naechster - 1]} säen/pflanzen", namen(bald_saat)))

    # Düngen im Sommer, Ernte
    if 6 <= m <= 8:
        stark = [pf(pid)["name"] for pid, _ in aktiv if pf(pid).get("zehrer") == "stark"]
        if stark and heute.isocalendar()[1] % 2 == 0:
            aufgaben.append(aufgabe("mdi:bottle-tonic-plus", "#A0522D", "Düngen", f"{namen(stark)}: Flüssigdünger oder Brennnesseljauche (1:10)."))
    ernte = [pf(pid)["name"] for pid, _ in aktiv if m in pf(pid).get("ernte", [])]
    if ernte:
        aufgaben.append(aufgabe("mdi:basket-outline", "#FF9500", "Erntezeit", namen(ernte)))

    # Jahreszeit
    if m in (10, 11):
        aufgaben.append(aufgabe("mdi:leaf", "#8E8E93", "Herbst im Garten",
                                "Abgeerntetes raus, Hochbeete mit 3–5 cm Kompost auffüllen, freie Erdhaufen mit Laub abdecken."))
        if m == 11 and heute.day >= 15:
            bald.append(aufgabe("mdi:water-off", "#8E8E93", "Tropfschlauch und Pumpe winterfest machen", "Vor dem ersten Dauerfrost entleeren."))
    if m == 2 or (m == 3 and heute.day < 15):
        aufgaben.append(aufgabe("mdi:shovel", "#8E8E93", "Frühjahr vorbereiten", "Hochbeete mit Kompost auffrischen, Saatgut und Anzuchterde besorgen."))

    print(json.dumps({"aufgaben": aufgaben[:8], "bald": bald[:4], "stand": heute.isoformat()}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"aufgaben": [], "bald": [], "fehler": f"{type(fehler).__name__}: {fehler}"[:200]}, ensure_ascii=False))
