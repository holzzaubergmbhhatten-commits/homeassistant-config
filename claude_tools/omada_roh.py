"""Direkte Aufrufe an den Omada-Controller (unabhängig davon, welche Version der Omada-Bibliothek in Home Assistant
steckt – ältere Versionen kennen manche Befehle noch nicht). Wird von omada_fest.py und kamera_retten.py benutzt."""


async def seiten(sc, pfad):
    api = sc._api
    url = api.format_url(pfad, sc._site_id)
    if hasattr(api, "iterate_pages"):
        return [x async for x in api.iterate_pages(url)]
    ergebnis, seite = [], 1
    while True:
        r = await api.request("get", url, params={"currentPage": seite, "currentPageSize": 100})
        daten = r.get("data", []) if isinstance(r, dict) else (r or [])
        ergebnis += daten
        if not isinstance(r, dict) or len(ergebnis) >= int(r.get("totalRows", 0) or 0) or not daten:
            return ergebnis
        seite += 1


async def netze(sc):
    """[(id, subnetz)] der LAN-Netze, z. B. ("abc…", "192.168.0.1/24")."""
    return [(n.get("id"), n.get("gatewaySubnet") or n.get("subnet")) for n in await seiten(sc, "setting/lan/networks")]


async def details(sc, mac):
    return await sc._api.request("get", sc._api.format_url(f"clients/{mac}", sc._site_id))


async def fest(sc, mac, netz_id, ip):
    await sc._api.request("patch", sc._api.format_url(f"clients/{mac}", sc._site_id),
                          json={"ipSetting": {"useFixedAddr": True, "netId": netz_id, "ip": ip}})


async def neu_verbinden(sc, mac):
    await sc._api.request("post", sc._api.format_url(f"cmd/clients/{mac}/reconnect", sc._site_id))


def drahtlos(client):
    roh = getattr(client, "raw_data", None) or getattr(client, "_data", {}) or {}
    return bool(roh.get("wireless", getattr(client, "is_wireless", False)))
