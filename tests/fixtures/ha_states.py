"""Fixture: meshcore-ha-entiteiten van de repeater (echte entiteitsnamen uit het HA-register)."""
import datetime
PFX, SLUG, NAME = "a1b2c3d4e5", "nl_xx_town_rptr_01", "NL|XX|TOWN|RPTR|01"
KEY = PFX + "0e" * 27 + "ab"

def iso(ts): return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()

def s(domain, key, state, attrs=None, ts=0, prefix=PFX, slug=SLUG, name=NAME):
    eid = f"{domain}.meshcore_{prefix}_{key}" + (f"_{slug}" if slug else "")
    a = {"friendly_name": f"MeshCore Repeater: {name} ({prefix[:6]}) {key}"}; a.update(attrs or {})
    return {"entity_id": eid, "state": str(state), "attributes": a, "last_updated": iso(ts), "last_changed": iso(ts)}

def repeater_states(now, stats_key="2026-09-21T18:30:00", mv=3920, age=900):
    ts = now - age
    return [
        s("sensor", "bat", f"{mv / 1000:.2f}", {"raw_millivolts": mv, "last_updated": stats_key}, ts),
        s("sensor", "battery_percentage", "78", None, ts), s("sensor", "uptime", "18455.5", None, ts),
        s("sensor", "airtime", "410.2", None, ts), s("sensor", "airtime_utilization", "1.85", None, ts),
        s("sensor", "nb_sent", "20412", None, ts), s("sensor", "nb_recv", "98211", None, ts),
        s("sensor", "last_rssi", "-96", None, ts), s("sensor", "last_snr", "7.25", None, ts), s("sensor", "noise_floor", "-112", None, ts),
        s("sensor", "ch1_temperature", "21.4", None, ts), s("sensor", "ch1_voltage", "3.91", None, ts),
        s("binary_sensor", "online", "on", None, ts),
        s("sensor", "neighbor_count", 3, None, ts, slug=None),
        s("sensor", "neighbor_984d7b", "9.5", {"pubkey_prefix": "984d7b0a11cc", "resolved_name": "NL-AB-RP02", "secs_ago": 300}, ts, slug=None),
        s("sensor", "neighbor_a98031", "-2.25", {"pubkey_prefix": "a98031aa22bb", "resolved_name": "", "secs_ago": 7200}, ts, slug=None),
        s("sensor", "neighbor_c5f9b3", "12.0", {"pubkey_prefix": "c5f9b3ff00aa", "resolved_name": "BE-Nabij", "secs_ago": 60}, ts, slug=None),
        s("sensor", "neighbor_11ab02", "unavailable", {"pubkey_prefix": "11ab02", "secs_ago": 90000}, ts, slug=None),
        {"entity_id": "binary_sensor.meshcore_be2440_contact_x", "state": "fresh", "attributes": {"public_key": KEY, "type": 2, "adv_name": NAME, "node_type_str": "Repeater"}, "last_updated": iso(now)},
    ]

def room_states(now):
    p, sl, nm = "f6e5d4c3b2", "home_room", "Home Room"
    return [s("sensor", "bat", "4.05", {"raw_millivolts": 4050}, now - 600, prefix=p, slug=sl, name=nm),
            {"entity_id": "binary_sensor.meshcore_x_contact", "state": "fresh", "attributes": {"public_key": p + "77" * 27, "type": 3, "adv_name": nm}, "last_updated": iso(now)}]
