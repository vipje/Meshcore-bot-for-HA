"""Shared NDW DATEX II traffic-situations fetcher, used by file_command.py and
wegwerk_command.py.

Source: https://opendata.ndw.nu/actueel_beeld.xml.gz - free, no key, one
national dump (~1150 situations, ~400KB uncompressed) covering traffic jams,
accidents, obstructions and roadworks together. Cached briefly in-memory
since it's a real-time feed and both commands would otherwise each re-fetch
the full file on every call.
"""

import gzip
import time
import xml.etree.ElementTree as ET
from typing import Any, Optional

import aiohttp

_FEED_URL = "https://opendata.ndw.nu/actueel_beeld.xml.gz"
_CACHE_SECONDS = 120

_NS = {
    "sit": "http://datex2.eu/schema/3/situation",
    "loc": "http://datex2.eu/schema/3/locationReferencing",
    "com": "http://datex2.eu/schema/3/common",
}

_DELAY_LABELS = {
    "lessThanTenMinutes": "<10 min",
    "betweenTenMinutesAndThirtyMinutes": "10-30 min",
    "betweenThirtyMinutesAndOneHour": "30-60 min",
    "moreThanOneHour": ">1 uur",
}

_cache: dict[str, Any] = {"situations": None, "fetched_at": 0.0}


async def get_situations(session: aiohttp.ClientSession) -> list[dict]:
    """Return all parsed NDW situations, using a short-lived in-memory cache."""
    now = time.time()
    if _cache["situations"] is not None and (now - _cache["fetched_at"]) < _CACHE_SECONDS:
        return _cache["situations"]

    async with session.get(_FEED_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        resp.raise_for_status()
        raw = await resp.read()
    xml_bytes = gzip.decompress(raw)
    root = ET.fromstring(xml_bytes)

    situations: list[dict] = []
    # ElementTree has no parent axis, so walk sit:situation (which carries
    # overallSeverity) and pull its situationRecord children, rather than
    # iterating situationRecord directly and trying to look upward.
    for situation in root.iter(f"{{{_NS['sit']}}}situation"):
        severity_el = situation.find("sit:overallSeverity", _NS)
        severity = severity_el.text if severity_el is not None else None

        record = situation.find("sit:situationRecord", _NS)
        if record is None:
            continue

        record_type = record.get(f"{{http://www.w3.org/2001/XMLSchema-instance}}type", "")
        record_type = record_type.split(":")[-1]

        pos_list_el = record.find(".//loc:posList", _NS)
        lat: Optional[float] = None
        lon: Optional[float] = None
        if pos_list_el is not None and pos_list_el.text:
            parts = pos_list_el.text.split()
            if len(parts) >= 2:
                try:
                    lat, lon = float(parts[0]), float(parts[1])
                except ValueError:
                    pass
        if lat is None:
            point_el = record.find(".//loc:pointCoordinates", _NS)
            if point_el is not None:
                lat_el = point_el.find("loc:latitude", _NS)
                lon_el = point_el.find("loc:longitude", _NS)
                if lat_el is not None and lon_el is not None:
                    try:
                        lat, lon = float(lat_el.text), float(lon_el.text)
                    except (TypeError, ValueError):
                        pass
        if lat is None or lon is None:
            continue

        delay_band_el = record.find(".//sit:delayBand", _NS)
        delay_label = _DELAY_LABELS.get(delay_band_el.text) if delay_band_el is not None and delay_band_el.text else None

        situations.append(
            {
                "type": record_type,
                "severity": severity,
                "delay_label": delay_label,
                "lat": lat,
                "lon": lon,
            }
        )

    _cache["situations"] = situations
    _cache["fetched_at"] = now
    return situations
