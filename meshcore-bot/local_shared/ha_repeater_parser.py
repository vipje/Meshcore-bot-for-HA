#!/usr/bin/env python3
"""Read what meshcore-ha knows about repeaters out of Home Assistant's states (see ha_repeater_service.py).

Pure functions, no I/O: they take the list that `GET /api/states` returns. The entity names and attributes
come from meshcore-ha's own code (custom_components/meshcore/sensor.py):

    sensor.meshcore_<10 hex of the key>_<metric>_<slug of the repeater name>     e.g. ..._bat_nl_xx_town_rptr_01
    sensor.meshcore_<10 hex>_neighbor_<6 hex>        state = SNR in dB; attributes pubkey_prefix, resolved_name, secs_ago
    sensor.meshcore_<10 hex>_neighbor_count

Units in Home Assistant: `bat` is in volts (attribute raw_millivolts = millivolts); `uptime`, `airtime` and
`rx_airtime` are in MINUTES (attribute raw_seconds when present). The full public key and the node type
(2 = repeater, 3 = room server) are attributes of the contact's binary sensor.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

ENTITY = re.compile(r"^(?:binary_)?sensor\.meshcore_(?P<prefix>[0-9a-f]{10})_(?P<rest>.+)$")
NEIGHBOR = re.compile(r"^neighbor_(?P<pk>[0-9a-f]{6})$")
FRIENDLY = re.compile(r"MeshCore Repeater: (?P<name>.+?) \((?P<pk6>[0-9a-f]{6})\)")
UNKNOWN = {"", "unknown", "unavailable", "none"}

NODE_REPEATER = 2
NODE_ROOM_SERVER = 3

# metric key in the entity id -> our field name
METRICS = {
    "bat": "battery_v",
    "battery_percentage": "battery_pct",
    "uptime": "uptime_min",
    "airtime": "airtime_min",
    "airtime_utilization": "airtime_util",
    "nb_sent": "nb_sent",
    "nb_recv": "nb_recv",
    "last_rssi": "last_rssi",
    "last_snr": "last_snr",
    "noise_floor": "noise_floor",
    "ch1_temperature": "temperature",
    "ch1_voltage": "ch1_voltage",
}


def num(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in UNKNOWN:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_time(value: Any) -> Optional[float]:
    """Unix time of an ISO timestamp from a Home Assistant state (they carry a UTC offset)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _split_metric(rest: str, slug: str) -> Optional[str]:
    """`bat_nl_xx_town_rptr_01` with slug `nl_xx_town_rptr_01` -> `bat`."""
    if slug and rest.endswith("_" + slug):
        return rest[: -len(slug) - 1]
    return None


def parse_states(states: list, now: Optional[float] = None) -> dict:
    """Every repeater-like device (one that has a battery sensor) found in `states`, by its 10-hex prefix.

    Each value: {prefix, name, public_key, node_type, battery_mv, battery_pct, uptime_s, airtime_s, ...,
    neighbors: [{prefix, name, snr, secs_ago}], stats_key, stats_age_s}. Missing values are None."""
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    by_prefix: dict = {}
    for st in states or []:
        eid = str(st.get("entity_id", ""))
        m = ENTITY.match(eid)
        if m:
            by_prefix.setdefault(m.group("prefix"), []).append((m.group("rest"), st))

    # full keys and node types: any state whose attributes carry a public_key (the contact's binary sensor)
    keys: dict = {}
    for st in states or []:
        attrs = st.get("attributes") or {}
        pk = str(attrs.get("public_key") or "").lower()
        if len(pk) >= 10 and re.fullmatch(r"[0-9a-f]+", pk):
            info = keys.setdefault(pk[:10], {"public_key": pk, "type": None, "name": None})
            if len(pk) > len(info["public_key"]):
                info["public_key"] = pk
            if attrs.get("type") is not None and info["type"] is None:
                try:
                    info["type"] = int(attrs["type"])
                except (TypeError, ValueError):
                    pass
            if attrs.get("adv_name") and not info["name"]:
                info["name"] = str(attrs["adv_name"])

    out: dict = {}
    for prefix, items in by_prefix.items():
        bat = next(((rest, st) for rest, st in items if rest.startswith("bat_") and not st["entity_id"].startswith("binary_")), None)
        if bat is None:
            continue   # not a repeater/room stat device (the radio itself, plain contacts)
        slug = bat[0][len("bat_"):]
        info = keys.get(prefix, {})
        friendly = FRIENDLY.search(str((bat[1].get("attributes") or {}).get("friendly_name") or ""))
        rep = {
            "prefix": prefix,
            "name": (friendly.group("name") if friendly else None) or info.get("name") or slug.replace("_", " "),
            "public_key": info.get("public_key") or prefix,
            "node_type": info.get("type"),
            "neighbors": [],
        }
        for rest, st in items:
            metric = _split_metric(rest, slug)
            if metric in METRICS:
                rep[METRICS[metric]] = num(st.get("state"))
            elif metric == "online":
                rep["online"] = str(st.get("state")).lower() == "on"
            elif rest == "neighbor_count":       # this one has no repeater name in its entity id
                rep["neighbor_count"] = num(st.get("state"))
            else:
                nb = NEIGHBOR.match(rest)
                if nb and not st["entity_id"].startswith("binary_"):
                    attrs = st.get("attributes") or {}
                    snr = num(st.get("state"))
                    secs = num(attrs.get("secs_ago"))
                    rep["neighbors"].append({
                        "prefix": str(attrs.get("pubkey_prefix") or nb.group("pk")).lower(),
                        "name": str(attrs.get("resolved_name") or ""),
                        "snr": snr,
                        "secs_ago": int(secs) if secs is not None else None,
                    })
        # exact figures: prefer the attributes over the rounded state
        battery_attrs = bat[1].get("attributes") or {}
        mv = num(battery_attrs.get("raw_millivolts"))
        rep["battery_mv"] = int(mv) if mv is not None else (int(round(rep["battery_v"] * 1000)) if rep.get("battery_v") else None)
        for field, key in (("uptime_s", "uptime"), ("airtime_s", "airtime")):
            item = next((st for rest, st in items if _split_metric(rest, slug) == key and not st["entity_id"].startswith("binary_")), None)
            secs = num(((item or {}).get("attributes") or {}).get("raw_seconds")) if item else None
            minutes = rep.get(f"{key}_min")
            rep[field] = int(secs) if secs is not None else (int(round(minutes * 60)) if minutes is not None else None)
        # how old is this data? the battery sensor changes with every status reply from the repeater
        rep["stats_key"] = str(battery_attrs.get("last_updated") or bat[1].get("last_updated") or "")
        changed = parse_time(bat[1].get("last_updated"))
        rep["stats_age_s"] = int(now - changed) if changed is not None else None
        rep["neighbors"].sort(key=lambda n: (n["snr"] is None, -(n["snr"] or 0)))
        out[prefix] = rep
    return out


def is_repeater(rep: dict) -> bool:
    """A repeater, or a device whose type is unknown; room servers (type 3) are left out by default."""
    return rep.get("node_type") in (None, NODE_REPEATER)


def select(repeaters: dict, wanted: list) -> list:
    """The repeaters to report on. `wanted` = prefixes from the card (empty = every repeater found)."""
    wanted = [w.strip().lower() for w in wanted or [] if w.strip()]
    if wanted:
        return [r for p, r in sorted(repeaters.items()) if any(p.startswith(w) or r["public_key"].startswith(w) for w in wanted)]
    return [r for _, r in sorted(repeaters.items()) if is_repeater(r)]


# ---------------------------------------------------------------------------------------------- text

def dec(value: float, translate, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", translate("commands.rptr.decimal_sep"))


def duration(seconds: Optional[float], translate) -> str:
    if seconds is None:
        return "?"
    s = int(seconds)
    if s < 3600:
        return f"{s // 60}{translate('commands.rptr.unit_m')}"
    if s < 86400:
        return f"{s // 3600}{translate('commands.rptr.unit_h')}"
    return f"{s // 86400}{translate('commands.rptr.unit_d')} {(s % 86400) // 3600}{translate('commands.rptr.unit_h')}"


def age(seconds: Optional[float], translate) -> str:
    if seconds is None:
        return translate("commands.rptr.age_unknown")
    if seconds < 90:
        return translate("commands.rptr.age_just_now")
    if seconds < 5400:
        return translate("commands.rptr.age_minutes", n=round(seconds / 60))
    return translate("commands.rptr.age_hours", n=round(seconds / 3600))


def fit(text: str, limit: int = 140) -> str:
    if len(text.encode("utf-8")) <= limit:
        return text
    while text and len((text + "…").encode("utf-8")) > limit:
        text = text[:-1]
    return text + "…"


def summary(rep: dict, translate, stale_after_s: int = 3 * 3600) -> str:
    """One line for `rptr`: battery, uptime, airtime, neighbours, and how old the data is."""
    parts = []
    if rep.get("battery_v") is not None:
        pct = f" ({int(rep['battery_pct'])}%)" if rep.get("battery_pct") is not None else ""
        parts.append(f"{dec(rep['battery_v'], translate, 2)} V{pct}")
    if rep.get("uptime_s") is not None:
        parts.append(translate("commands.rptr.up", duration=duration(rep["uptime_s"], translate)))
    if rep.get("airtime_util") is not None:
        parts.append(translate("commands.rptr.airtime", pct=dec(rep["airtime_util"], translate)))
    if rep.get("neighbor_count") is not None:
        parts.append(translate("commands.rptr.neighbours_count", n=int(rep["neighbor_count"])))
    elif rep["neighbors"]:
        parts.append(translate("commands.rptr.neighbours_count", n=len(rep["neighbors"])))
    a = rep.get("stats_age_s")
    age_text = age(a, translate)
    parts.append(age_text if a is None or a < stale_after_s else translate("commands.rptr.stale_warning", age=age_text))
    return f"{rep['name']}: " + " | ".join(parts)


def neighbours_text(rep: dict, translate, limit: int = 130) -> str:
    """`rptr buren`: the neighbours with the best signal first, as many as fit in one message, and how many were left out."""
    items = [n for n in rep["neighbors"] if n.get("snr") is not None]
    head = translate("commands.rptr.neighbours_header", name=rep["name"], n=len(rep["neighbors"]))
    pieces = [f"{(n['name'] or n['prefix'][:6])} {dec(n['snr'], translate)} dB" for n in items]

    def build(shown: int) -> str:
        text = head + " | ".join(pieces[:shown])
        left = len(pieces) - shown
        return text + (f" | +{left}" if left > 0 else "")

    shown = len(pieces)
    while shown > 0 and len(build(shown).encode("utf-8")) > limit:
        shown -= 1
    return build(shown) if shown > 0 else head + translate("commands.rptr.no_data")


# ---------------------------------------------------------------------------------------------- history
def slope_per_day(rows: list) -> Optional[float]:
    """Volts per day, least squares over [(unix time, mV)]; None when the readings span less than 6 hours."""
    pts = [(t, mv) for t, mv in rows if mv is not None]
    if len(pts) < 3 or pts[-1][0] - pts[0][0] < 6 * 3600:
        return None
    n = len(pts)
    mt = sum(t for t, _ in pts) / n
    mv = sum(v for _, v in pts) / n
    den = sum((t - mt) ** 2 for t, _ in pts)
    if den == 0:
        return None
    per_second = sum((t - mt) * (v - mv) for t, v in pts) / den
    return per_second * 86400 / 1000.0


def period_label(hours: int, translate) -> str:
    return (
        translate("commands.rptr.period_hours", n=hours)
        if hours < 48 else translate("commands.rptr.period_days", n=round(hours / 24))
    )


def battery_text(name: str, rows: list, hours: int, translate, low_mv: int = 3600) -> str:
    """`rptr accu`: now, lowest, highest and the trend over the period, from the stored readings [(unix time, mV)]."""
    pts = [(t, v) for t, v in rows if v]
    head = translate("commands.rptr.battery_header", name=name, period=period_label(hours, translate))
    if len(pts) < 2:
        return fit(translate("commands.rptr.battery_too_few", name=name, n=len(pts)))
    now_v = pts[-1][1] / 1000.0
    lo = min(v for _, v in pts) / 1000.0
    hi = max(v for _, v in pts) / 1000.0
    parts = [
        translate("commands.rptr.battery_now", v=dec(now_v, translate, 2)),
        translate("commands.rptr.battery_min", v=dec(lo, translate, 2)),
        translate("commands.rptr.battery_max", v=dec(hi, translate, 2)),
    ]
    slope = slope_per_day(pts)
    if slope is None:
        parts.append(translate("commands.rptr.trend_unknown"))
    elif abs(slope) < 0.005:
        parts.append(translate("commands.rptr.trend_stable"))
    else:
        text = f"{'+' if slope > 0 else '-'}{dec(abs(slope), translate, 2)}" + translate("commands.rptr.trend_v_per_day")
        if slope < 0 and now_v * 1000 > low_mv:
            days = (now_v * 1000 - low_mv) / 1000.0 / -slope
            if days < 60:
                text += translate("commands.rptr.trend_low_in", days=int(round(days)))
        parts.append(text)
    parts.append(translate("commands.rptr.measurements", n=len(pts)))
    return fit(head + " | ".join(parts))
