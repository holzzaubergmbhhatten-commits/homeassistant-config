#!/usr/bin/env python3
"""Kameras mit verrutschter Adresse selbst wiederfinden und reparieren (ohne dass Marco in Apps muss).

Problem: Nach einem Router-Neustart bekommen WLAN-Kameras manchmal eine neue Adresse. Home Assistant sucht sie
aber unter der alten (Integration „Generic Camera“) → „nicht erreichbar“.

Ablauf je Kamera (Generic Camera mit rtsp-Adresse):
  1. Antwortet die Kamera unter ihrer Adresse (RTSP mit ihrem Benutzer/Passwort)? → alles gut, MAC merken.
  2. Sonst: neue Adresse suchen – zuerst über die gemerkte MAC im Omada-Controller, sonst alle Geräte im Heimnetz
     mit offenem Kamera-Port (554) mit Benutzer/Passwort/Pfad dieser Kamera durchprobieren.
  3. Gefunden → im Omada-Controller die ALTE Adresse für die Kamera festmachen; ein anderes WLAN-Gerät, das die alte
     Adresse gerade hat, kurz neu verbinden lassen (bekommt eine andere), dann die Kamera neu verbinden lassen.
     So stimmt die Adresse in Home Assistant wieder, ohne dass dort etwas geändert werden muss.
Nur lesen: /config/.storage (Kamera-Zugang, Omada-Zugang). Gemerkte MACs: /config/kamera_macs.json (lokal).
Ausgabe JSON: {"ok", "kameras": [{name, ip, status, neu_ip, hinweis}]}
status: ok | repariert | gefunden | nicht_gefunden | fehler
"""
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
MACS = "/config/kamera_macs.json"
GEMELDET = "/config/.kamera_retten_gemeldet.json"


def lade(name):
    with open(os.path.join("/config/.storage", name), encoding="utf-8") as f:
        return json.load(f)["data"]


def kameras():
    eintraege = lade("core.config_entries")["entries"]
    entitaeten = {e["config_entry_id"]: e["entity_id"] for e in lade("core.entity_registry")["entities"]
                  if e["entity_id"].startswith("camera.")}
    liste = []
    for e in eintraege:
        if e["domain"] != "generic" or e.get("disabled_by"):
            continue
        o = {**e.get("data", {}), **e.get("options", {})}
        quelle = (o.get("stream_source") or "").strip()
        if not quelle.startswith("rtsp") or "{{" in quelle:
            continue
        t = urllib.parse.urlsplit(quelle)
        benutzer = urllib.parse.unquote(t.username or "") or o.get("username") or ""
        passwort = urllib.parse.unquote(t.password or "") or o.get("password") or ""
        liste.append({"name": e.get("title") or entitaeten.get(e["entry_id"], "Kamera"),
                      "entity": entitaeten.get(e["entry_id"], ""), "ip": t.hostname, "port": t.port or 554,
                      "pfad": t.path or "/", "benutzer": benutzer, "passwort": passwort})
    return liste


def rtsp_ok(ip, k, zeit=3.0):
    """DESCRIBE mit Benutzer/Passwort (Digest oder Basic). True = Kamera mit diesem Zugang antwortet."""
    uri = f"rtsp://{ip}:{k['port']}{k['pfad']}"

    def anfrage(sock, cseq, zusatz=""):
        sock.sendall(f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: {cseq}\r\nAccept: application/sdp\r\n{zusatz}\r\n".encode())
        daten = b""
        while b"\r\n\r\n" not in daten and len(daten) < 20000:
            stueck = sock.recv(4096)
            if not stueck:
                break
            daten += stueck
        return daten.decode("latin-1", "replace")

    try:
        with socket.create_connection((ip, k["port"]), timeout=zeit) as s:
            s.settimeout(zeit)
            antwort = anfrage(s, 1)
            if antwort.startswith("RTSP/1.0 200"):
                return True
            m = re.search(r'WWW-Authenticate:\s*Digest\s+([^\r\n]+)', antwort, re.I)
            if m:
                felder = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
                ha1 = hashlib.md5(f"{k['benutzer']}:{felder.get('realm', '')}:{k['passwort']}".encode()).hexdigest()
                ha2 = hashlib.md5(f"DESCRIBE:{uri}".encode()).hexdigest()
                resp = hashlib.md5(f"{ha1}:{felder.get('nonce', '')}:{ha2}".encode()).hexdigest()
                kopf = (f'Authorization: Digest username="{k["benutzer"]}", realm="{felder.get("realm", "")}", '
                        f'nonce="{felder.get("nonce", "")}", uri="{uri}", response="{resp}"\r\n')
            elif re.search(r"WWW-Authenticate:\s*Basic", antwort, re.I):
                import base64
                kopf = "Authorization: Basic " + base64.b64encode(f"{k['benutzer']}:{k['passwort']}".encode()).decode() + "\r\n"
            else:
                return False
            return anfrage(s, 2, kopf).startswith("RTSP/1.0 200")
    except OSError:
        return False


def port_offen(ziel):
    ip, port = ziel
    try:
        with socket.create_connection((ip, port), timeout=0.6):
            return ip
    except OSError:
        return None


def omada_zugang():
    for e in lade("core.config_entries")["entries"]:
        if e["domain"] == "tplink_omada" and not e.get("disabled_by"):
            d = {**e.get("data", {}), **e.get("options", {})}
            return d.get("host"), d.get("username"), d.get("password"), d.get("verify_ssl", False), d.get("site")
    return None


async def omada(aufgabe):
    """aufgabe(sc, clients_nach_ip, clients_nach_mac, netze) im Omada-Kontext ausführen."""
    from tplink_omada_client import OmadaClient
    z = omada_zugang()
    if not z:
        raise RuntimeError("Integration „TP-Link Omada“ fehlt")
    host, benutzer, passwort, ssl_pruefen, site_id = z
    host = host if host.startswith("http") else "https://" + host
    async with OmadaClient(host, benutzer, passwort, verify_ssl=bool(ssl_pruefen)) as client:
        await client.login()
        sites = await client.get_sites()
        site = next((s for s in sites if s.id == site_id), None) or sites[0]
        sc = await client.get_site_client(site)
        nach_ip, nach_mac = {}, {}
        async for c in sc.get_connected_clients():
            nach_mac[c.mac] = c
            if c.ip:
                nach_ip[c.ip] = c
        import omada_roh
        netze = await omada_roh.netze(sc)
        return await aufgabe(sc, nach_ip, nach_mac, netze)


async def main():
    import omada_roh
    liste = kameras()
    try:
        gemerkt = json.load(open(MACS, encoding="utf-8"))
    except (OSError, ValueError):
        gemerkt = {}
    for k in liste:
        k["ok"] = rtsp_ok(k["ip"], k)
    # Zwei Kameras mit derselben Adresse = Verwechslung (gleicher Zugang bei allen Tapo-Kameras). Behalten darf sie nur die,
    # deren Titel zur Adresse passt; die andere gilt als „verrutscht“ und ihre gemerkte MAC als unsicher.
    for ip in {k["ip"] for k in liste}:
        gleiche = [k for k in liste if k["ip"] == ip]
        if len(gleiche) > 1:
            behalten = next((k for k in gleiche if k["name"].replace("_", ".") == ip), gleiche[0])
            for k in gleiche:
                if k is not behalten:
                    k["ok"] = False
                    k["doppelt"] = True
                    gemerkt.pop(k["entity"] or k["name"], None)
    kaputt = [k for k in liste if not k["ok"]]

    async def arbeit(sc, nach_ip, nach_mac, netze):
        ergebnis = []
        for k in liste:   # funktionierende Kameras: MAC merken (für das nächste Mal)
            if k["ok"] and k["ip"] in nach_ip:
                gemerkt[k["entity"] or k["name"]] = nach_ip[k["ip"]].mac
        belegt = {k["ip"] for k in liste if k["ok"] or k.get("doppelt")}
        kandidaten = None
        for k in kaputt:
            eintrag = {"name": k["name"], "ip": k["ip"], "status": "nicht_gefunden", "neu_ip": None, "hinweis": ""}
            neu_ip = None
            mac = gemerkt.get(k["entity"] or k["name"])
            if mac and mac in nach_mac and nach_mac[mac].ip and nach_mac[mac].ip != k["ip"] and nach_mac[mac].ip not in belegt \
                    and rtsp_ok(nach_mac[mac].ip, k):
                neu_ip = nach_mac[mac].ip
            if not neu_ip:
                if kandidaten is None:   # einmal das Heimnetz nach offenen Kamera-Ports absuchen
                    netz = ipaddress.ip_network(k["ip"] + "/24", strict=False)
                    with ThreadPoolExecutor(max_workers=64) as pool:
                        kandidaten = [ip for ip in pool.map(port_offen, [(str(h), k["port"]) for h in netz.hosts()]) if ip]
                treffer = [ip for ip in kandidaten if ip not in belegt and ip != k["ip"] and rtsp_ok(ip, k)]
                if len(treffer) == 1:
                    neu_ip = treffer[0]
                elif len(treffer) > 1:
                    eintrag["hinweis"] = "mehrere Kameras mit gleichem Zugang gefunden: " + ", ".join(treffer)
            if not neu_ip:
                ergebnis.append(eintrag)
                continue
            belegt.add(neu_ip)
            eintrag.update(status="gefunden", neu_ip=neu_ip)
            c = nach_ip.get(neu_ip)
            if not c:
                eintrag["hinweis"] = "im Omada-Controller nicht gefunden"
                ergebnis.append(eintrag)
                continue
            gemerkt[k["entity"] or k["name"]] = c.mac
            if k.get("doppelt"):
                eintrag["hinweis"] = (f"In Home Assistant stand die Adresse einer anderen Kamera. Diese Kamera ist jetzt unter {neu_ip} – "
                                      f"in Home Assistant bei der Kamera die Adresse auf {neu_ip} ändern.")
                ergebnis.append(eintrag)
                continue
            netz = next((n for n in netze if n[1] and
                         ipaddress.ip_address(k["ip"]) in ipaddress.ip_network(n[1], strict=False)), None)
            besetzt = nach_ip.get(k["ip"])
            if not netz or (besetzt and besetzt.mac != c.mac and not omada_roh.drahtlos(besetzt)):
                # alte Adresse geht nicht (fest verkabeltes Gerät sitzt darauf) → neue Adresse festhalten
                if netz:
                    await omada_roh.fest(sc, c.mac, netz[0], neu_ip)
                eintrag["hinweis"] = (f"Die alte Adresse {k['ip']} ist von einem Kabel-Gerät belegt. Kamera jetzt fest auf {neu_ip} – "
                                      f"in Home Assistant bei der Kamera die Adresse auf {neu_ip} ändern.")
                ergebnis.append(eintrag)
                continue
            await omada_roh.fest(sc, c.mac, netz[0], k["ip"])
            if besetzt and besetzt.mac != c.mac:
                await omada_roh.neu_verbinden(sc, besetzt.mac)
                await asyncio.sleep(20)
            if omada_roh.drahtlos(c):
                await omada_roh.neu_verbinden(sc, c.mac)
                for _ in range(12):   # bis zu 2 Minuten warten, bis sie unter der alten Adresse antwortet
                    await asyncio.sleep(10)
                    if rtsp_ok(k["ip"], k):
                        eintrag["status"] = "repariert"
                        break
                if eintrag["status"] != "repariert":
                    eintrag["hinweis"] = "alte Adresse festgemacht – die Kamera übernimmt sie beim nächsten Neuverbinden"
            else:
                eintrag["hinweis"] = "Kabel-Kamera: übernimmt die alte Adresse beim nächsten Neustart"
            ergebnis.append(eintrag)
        return ergebnis

    if kaputt or not gemerkt:
        try:
            repariert = await omada(arbeit)
        except Exception as fehler:  # noqa: BLE001
            repariert = [{"name": k["name"], "ip": k["ip"], "status": "fehler", "neu_ip": None, "hinweis": str(fehler)[:150]} for k in kaputt]
    else:
        repariert = []
    tmp = MACS + ".tmp"
    json.dump(gemerkt, open(tmp, "w", encoding="utf-8"))
    os.replace(tmp, MACS)
    status = {r["name"]: r for r in repariert}
    aus = [status.get(k["name"], {"name": k["name"], "ip": k["ip"], "status": "ok", "neu_ip": None, "hinweis": ""}) for k in liste]
    # melden = nur, wenn sich etwas geändert hat (kein Dauerfeuer bei einer Kamera, die länger weg ist)
    try:
        alt = json.load(open(GEMELDET, encoding="utf-8"))
    except (OSError, ValueError):
        alt = {}
    neu = {}
    for a in aus:
        kennung = f"{a['status']}|{a['neu_ip']}"
        a["melden"] = a["status"] != "ok" and alt.get(a["name"]) != kennung
        if a["status"] != "ok":
            neu[a["name"]] = kennung
    json.dump(neu, open(GEMELDET, "w", encoding="utf-8"))
    print(json.dumps({"ok": True, "kameras": aus}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler": str(fehler)[:200]}, ensure_ascii=False))
