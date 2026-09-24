"""Parser voor meshcore-ha-entiteiten, met de echte entiteitsnamen van de repeater (uit het HA-register)."""
import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import json, sys
sys.path.insert(0, ADDON + "/local_shared")
import ha_repeater_parser as P

_CATALOG = json.load(open(ADDON + "/local_shared/local_translations/nl.json"))


def TR(key, **kwargs):
    node = _CATALOG
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return key
        node = node[part]
    return node.format(**kwargs) if isinstance(node, str) and kwargs else node

NOW = 1790010000.0
def iso(ts): return __import__("datetime").datetime.fromtimestamp(ts, __import__("datetime").timezone.utc).isoformat()

PFX, SLUG, NAME = "a1b2c3d4e5", "nl_xx_town_rptr_01", "NL|XX|TOWN|RPTR|01"
KEY = PFX + "0e" * 27 + "ab"           # 64 hex
def s(domain, key, state, attrs=None, ts=NOW - 900, prefix=PFX, slug=SLUG, name=NAME, pk6=None):
    eid = f"{domain}.meshcore_{prefix}_{key}" + (f"_{slug}" if slug else "")
    a = {"friendly_name": f"MeshCore Repeater: {name} ({(pk6 or prefix)[:6]}) {key}"}; a.update(attrs or {})
    return {"entity_id": eid, "state": str(state), "attributes": a, "last_updated": iso(ts), "last_changed": iso(ts)}

def repeater_states():
    st = [
        s("sensor", "bat", "3.92", {"raw_millivolts": 3920, "last_updated": "2026-09-21T18:30:00"}),
        s("sensor", "battery_percentage", "78"),
        s("sensor", "uptime", "18455.5", {"human_readable": "12d 19h 35m 30s"}),        # minuten, gebeurtenis-vorm zonder raw_seconds
        s("sensor", "airtime", "410.2"), s("sensor", "airtime_utilization", "1.85"),
        s("sensor", "nb_sent", "20412"), s("sensor", "nb_recv", "98211"),
        s("sensor", "last_rssi", "-96"), s("sensor", "last_snr", "7.25"), s("sensor", "noise_floor", "-112"),
        s("sensor", "ch1_temperature", "21.4"), s("sensor", "ch1_voltage", "3.91"),
        s("binary_sensor", "online", "on"),
        s("sensor", "neighbor_count", 3, slug=None),
        s("sensor", "neighbor_984d7b", "9.5", {"pubkey_prefix": "984d7b0a11cc", "resolved_name": "NL-AB-RP02", "secs_ago": 300}, slug=None),
        s("sensor", "neighbor_984d7b_seen", "300", slug=None),
        s("sensor", "neighbor_a98031", "-2.25", {"pubkey_prefix": "a98031aa22bb", "resolved_name": "", "secs_ago": 7200}, slug=None),
        s("sensor", "neighbor_c5f9b3", "12.0", {"pubkey_prefix": "c5f9b3ff00aa", "resolved_name": "BE-Nabij", "secs_ago": 60}, slug=None),
        s("sensor", "neighbor_11ab02", "unavailable", {"pubkey_prefix": "11ab02", "secs_ago": 90000}, slug=None),
        # het contact van de repeater: volledige sleutel en type
        {"entity_id": "binary_sensor.meshcore_be2440_contact_x", "state": "fresh", "attributes": {"public_key": KEY, "type": 2, "adv_name": NAME, "node_type_str": "Repeater"}, "last_updated": iso(NOW)},
    ]
    return st

def room_states():
    p, sl, nm = "f6e5d4c3b2", "home_room", "Home Room"
    return [s("sensor", "bat", "4.05", {"raw_millivolts": 4050}, prefix=p, slug=sl, name=nm), s("sensor", "uptime", "300", {"raw_seconds": 18000}, prefix=p, slug=sl, name=nm),
            {"entity_id": "binary_sensor.meshcore_x_contact", "state": "fresh", "attributes": {"public_key": p + "77" * 27, "type": 3, "adv_name": nm}, "last_updated": iso(NOW)}]

radio = [{"entity_id": "sensor.meshcore_5c6d7e_node_count_vip_home_assistent", "state": "354", "attributes": {}}, {"entity_id": "sensor.other_thing", "state": "1", "attributes": {}}]

fails = []
def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c: fails.append(m)

reps = P.parse_states(repeater_states() + room_states() + radio, now=NOW)
check(set(reps) == {PFX, "f6e5d4c3b2"}, f"alleen apparaten met een batterijsensor: {sorted(reps)}")
r = reps[PFX]
check(r["name"] == NAME and r["public_key"] == KEY and r["node_type"] == 2, "naam, volledige sleutel en type uit het contact")
check(r["battery_mv"] == 3920 and r["battery_v"] == 3.92 and r["battery_pct"] == 78, "batterij: mV uit het attribuut, volt en procent uit de status")
check(r["uptime_s"] == 1107330 and r["airtime_s"] == 24612, "uptime en airtime: minuten omgerekend naar seconden (geen raw_seconds)")
check(reps["f6e5d4c3b2"]["uptime_s"] == 18000, "raw_seconds wordt boven de afgeronde minuten verkozen")
check(r["airtime_util"] == 1.85 and r["nb_sent"] == 20412 and r["nb_recv"] == 98211 and r["last_snr"] == 7.25 and r["noise_floor"] == -112, "overige metingen kloppen")
check(r["temperature"] == 21.4 and r["ch1_voltage"] == 3.91 and r["online"] is True and r["neighbor_count"] == 3, "temperatuur, spanning, online en aantal buren")
check([n["prefix"][:6] for n in r["neighbors"]] == ["c5f9b3", "984d7b", "a98031", "11ab02"], "buren gesorteerd op sterkste signaal, onbekende SNR laatst")
check(r["neighbors"][0]["name"] == "BE-Nabij" and r["neighbors"][3]["snr"] is None, "buurnamen en 'unavailable' -> geen waarde")
check(all("_seen" not in n["prefix"] for n in r["neighbors"]) and len(r["neighbors"]) == 4, "de '_seen'-sensoren tellen niet als buur")
check(r["stats_age_s"] == 900 and r["stats_key"] == "2026-09-21T18:30:00", "leeftijd van de gegevens en de sleutel voor 'nieuwe meting'")
check([x["prefix"] for x in P.select(reps, [])] == [PFX], "standaard alleen repeaters (room server valt af)")
check([x["prefix"] for x in P.select(reps, ["f6e5d4"])] == ["f6e5d4c3b2"], "een prefix op de kaart selecteert ook een room server")
check([x["prefix"] for x in P.select(reps, [KEY[:12]])] == [PFX], "selecteren op (een deel van) de volledige sleutel")

# ontbrekende/kapotte gegevens
broken = P.parse_states([s("sensor", "bat", "unavailable"), s("sensor", "uptime", "unknown"), s("sensor", "neighbor_count", "x", slug=None)], now=NOW)[PFX]
check(broken["battery_mv"] is None and broken["uptime_s"] is None and broken["neighbor_count"] is None and broken["name"] == NAME, "onbeschikbare waarden geven None, geen fout")
check(P.parse_states([], now=NOW) == {} and P.parse_states(None) == {}, "lege invoer geeft niets")
noattr = P.parse_states([{"entity_id": f"sensor.meshcore_{PFX}_bat_{SLUG}", "state": "3.7"}], now=NOW)[PFX]
check(noattr["battery_mv"] == 3700 and noattr["name"] == "nl xx town rptr 01" and noattr["public_key"] == PFX, "zonder attributen: mV uit de volt, naam uit de slug")

# tekst
line = P.summary(r, TR)
print("   ", line, f"({len(line.encode())} bytes)")
check(line.startswith(NAME + ": 3,92 V (78%) | up 12d 19u | airtime 1,9% | 3 buren | 15 min oud"), "samenvatting in het Nederlands met decimale komma")
check(len(line.encode()) <= 140, "samenvatting past in één bericht")
stale = dict(r, stats_age_s=5 * 3600); check("LET OP: 5 u oud" in P.summary(stale, TR), "oude gegevens krijgen 'LET OP'")
nb = P.neighbours_text(r, TR); print("   ", nb, f"({len(nb.encode())} bytes)")
check(nb.startswith(f"{NAME} buren (4): BE-Nabij 12,0 dB | NL-AB-RP02 9,5 dB") and len(nb.encode()) <= 130, "buren-tekst: sterkste eerst en binnen de lengte")
check(P.neighbours_text(dict(r, neighbors=[]), TR).endswith("geen gegevens"), "geen buren: nette melding")
check(P.dec(3.0, TR) == "3,0" and P.duration(59, TR) == "0m" and P.duration(7200, TR) == "2u" and P.duration(90000, TR) == "1d 1u", "hulpfuncties")
print(f"\n{len(fails)} fouten"); sys.exit(1 if fails else 0)
