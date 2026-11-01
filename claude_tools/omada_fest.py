#!/usr/bin/env python3
"""Feste Adressen im Omada-Controller eintragen – damit Marco das nicht in der App machen muss.

Nimmt alle Geräte, die Home Assistant über ihre Adresse anspricht (claude_tools/ip_liste.py: Kameras, Shellys,
OC200 …), sucht sie im Omada-Controller (Clients) und trägt bei jedem die JETZIGE Adresse als feste Adresse ein
(„Feste IP-Adresse verwenden“). Es ändert sich also keine Adresse, sie wird nur festgehalten.

Aufruf: omada_fest.py plan        → nur anzeigen, was gemacht würde
        omada_fest.py ausfuehren  → eintragen
Zugang: der Omada-Benutzer der Home-Assistant-Integration „TP-Link Omada“ (aus /config/.storage, nur lesen).
Ausgabe JSON: {"ok", "neu": [{name, ip, mac}], "schon": [...], "fehlt": [...], "fehler": [...]}"""
import asyncio
import ipaddress
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def zugang():
    with open("/config/.storage/core.config_entries", encoding="utf-8") as f:
        for e in json.load(f)["data"]["entries"]:
            if e["domain"] == "tplink_omada" and not e.get("disabled_by"):
                d = {**e.get("data", {}), **e.get("options", {})}
                return d.get("host"), d.get("username"), d.get("password"), d.get("verify_ssl", False), d.get("site")
    raise RuntimeError("Integration „TP-Link Omada“ nicht gefunden")


def ziel_adressen():
    import io
    import contextlib
    import ip_liste
    puffer = io.StringIO()
    alt = sys.argv
    sys.argv = [alt[0]]
    try:
        with contextlib.redirect_stdout(puffer):
            ip_liste.main()
    finally:
        sys.argv = alt
    daten = json.loads(puffer.getvalue())
    namen = {}
    for g in daten.get("geraete", []):
        namen.setdefault(g["adresse"], g["name"])
    try:   # Home Assistant selbst (Browser, App und Monitor finden ihn unter dieser Adresse)
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        namen.setdefault(s.getsockname()[0], "Home Assistant")
        s.close()
    except OSError:
        pass
    return namen


async def main(ausfuehren):
    from tplink_omada_client import OmadaClient
    import omada_roh

    host, benutzer, passwort, ssl_pruefen, site_id = zugang()
    if not host.startswith("http"):
        host = "https://" + host
    ziele = ziel_adressen()
    ergebnis = {"ok": True, "neu": [], "schon": [], "fehlt": [], "fehler": []}
    async with OmadaClient(host, benutzer, passwort, verify_ssl=bool(ssl_pruefen)) as client:
        await client.login()
        sites = await client.get_sites()
        site = next((s for s in sites if s.id == site_id), None) or next((s for s in sites if "home" in s.name.lower()), None) or sites[0]
        sc = await client.get_site_client(site)
        netze = await omada_roh.netze(sc)
        nach_ip = {}
        async for c in sc.get_connected_clients():
            if c.ip:
                nach_ip[c.ip] = c
        for ip, name in sorted(ziele.items(), key=lambda x: tuple(int(t) for t in x[0].split("."))):
            c = nach_ip.get(ip)
            if not c:
                ergebnis["fehlt"].append({"name": name, "ip": ip})
                continue
            eintrag = {"name": name, "ip": ip, "mac": c.mac, "omada": c.name}
            try:
                roh = await omada_roh.details(sc, c.mac)
                fest = bool(roh.get("useFixedAddr") or (roh.get("ipSetting") or {}).get("useFixedAddr"))
                fest_ip = (roh.get("ipSetting") or {}).get("ip") or roh.get("fixedIp") or ip
                if fest and fest_ip == ip:
                    ergebnis["schon"].append(eintrag)
                    continue
                netz = next((n for n in netze if n[1] and
                             ipaddress.ip_address(ip) in ipaddress.ip_network(n[1], strict=False)), None)
                if not netz:
                    raise RuntimeError("kein passendes Netz")
                if ausfuehren:
                    await omada_roh.fest(sc, c.mac, netz[0], ip)
                ergebnis["neu"].append(eintrag)
            except Exception as fehler:  # noqa: BLE001
                eintrag["fehler"] = str(fehler)[:120]
                ergebnis["fehler"].append(eintrag)
    print(json.dumps(ergebnis, ensure_ascii=False))


MARKE = "/config/.omada_fest_vorgeschlagen_2"   # erst nach einem erfolgreichen Vorschlag gesetzt

if __name__ == "__main__":
    try:
        modus = sys.argv[1] if len(sys.argv) > 1 else "plan"
        if modus == "plan_einmal" and os.path.exists(MARKE):
            print(json.dumps({"ok": True, "still": True, "neu": [], "schon": [], "fehlt": [], "fehler": []}))
            sys.exit(0)
        asyncio.run(main(modus == "ausfuehren"))
        if modus == "plan_einmal":
            open(MARKE, "w").close()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"ok": False, "fehler_text": str(fehler)[:200]}, ensure_ascii=False))
