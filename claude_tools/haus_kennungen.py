#!/usr/bin/env python3
"""Findet die Entitäten, die sich nur über ihre Kennung erkennen lassen (Viessmann, Conel/SYR, Melder), und gibt sie
als JSON aus – für sensor.haus_kennungen (packages/haus_waechter.yaml). Vorlagen in Home Assistant sehen weder
unique_id noch translation_key, deshalb liest dieses Skript die Entitätsliste (.storage/core.entity_registry) nur lesend.

Ausgabe: {"pv_leistung": "sensor.…", "akku_stand": …, "conel_durchfluss": …, "conel_ventil": …, "conel_volumen": …,
          "conel_alarm": [...], "conel_warnung": [...], "wassermelder": [...], "rauchmelder": [...]}
"""
import json
import re

REGISTRY = "/config/.storage/core.entity_registry"

VIESSMANN = {"pv_leistung": ["photovoltaic_power_production_current"], "akku_stand": ["ess_state_of_charge"],
             "warmwasser": ["dhw_storage_temperature", "dhw_storage_top_temperature"],
             "warmwasser_einmal": ["activate_onetimecharge", "one_time_charge"]}
CONEL = {"conel_durchfluss": ["getflo"], "conel_ventil": ["getab", "getvlv"], "conel_volumen": ["getvol"]}
# Alarm/Warnung gibt es je Gerät (Conel-Absperrung und SafeFloor-Bodensensor) → Listen
CONEL_LISTEN = {"conel_alarm": ["getala"], "conel_warnung": ["getwrn"]}


def passt(e, n):
    return ((e.get("translation_key") or "").lower() == n
            or re.search(r"[-_.]" + n + r"$", e.get("unique_id") or "", re.I) is not None
            or re.search(r"_" + n + r"(_\d+)?$", e.get("entity_id") or "", re.I) is not None)


def main():
    with open(REGISTRY, encoding="utf-8") as f:
        alle = [e for e in json.load(f)["data"]["entities"] if not e.get("disabled_by")]
    aus = {}
    for plattform, tabelle in (("vicare", VIESSMANN), ("syr_connect", CONEL)):
        liste = [e for e in alle if e.get("platform") == plattform]
        for name, keys in tabelle.items():
            treffer = [e["entity_id"] for k in keys for e in liste if passt(e, k)]
            aus[name] = treffer[0] if treffer else ""
    if not aus.get("conel_volumen"):
        # Wasserzähler (Gesamtmenge) auch ohne bekannte Kennung: Conel-Sensor, der nur hochzählt
        zaehler = [e["entity_id"] for e in alle if e.get("platform") == "syr_connect" and e["entity_id"].startswith("sensor.")
                   and ((e.get("capabilities") or {}).get("state_class") == "total_increasing"
                        or (e.get("device_class") or e.get("original_device_class")) == "water")]
        aus["conel_volumen"] = zaehler[0] if zaehler else ""
    syr = [e for e in alle if e.get("platform") == "syr_connect" and e["entity_id"].startswith("sensor.")]
    for name, keys in CONEL_LISTEN.items():
        aus[name] = sorted({e["entity_id"] for k in keys for e in syr if passt(e, k)})
    klasse = lambda e: e.get("device_class") or e.get("original_device_class") or ""   # noqa: E731
    aus["wassermelder"] = sorted(e["entity_id"] for e in alle
                                 if e["entity_id"].startswith("binary_sensor.") and klasse(e) == "moisture")
    aus["rauchmelder"] = sorted(e["entity_id"] for e in alle
                                if e["entity_id"].startswith("binary_sensor.") and klasse(e) in ("smoke", "gas", "carbon_monoxide"))
    print(json.dumps(aus))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:  # noqa: BLE001
        print(json.dumps({"fehler": f"{type(fehler).__name__}: {fehler}"[:200]}))
