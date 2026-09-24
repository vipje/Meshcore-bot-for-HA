#!/usr/bin/env python3
"""
'straling' command for the MeshCore Bot.
Reports an indicative ambient radiation level near a place, from the free
Safecast API (community/citizen-science Geiger sensors, no key required).

RIVM/EURDEP only publish yearly averages or WMS map layers, not a simple
realtime JSON API, so Safecast is the practical choice here - this is
explicitly a rough, indicative reading, not an official measurement.
"""

from datetime import datetime
from statistics import median
from typing import Any

import aiohttp

from ..models import MeshMessage
from ..utils import geocode_city
from .base_command import BaseCommand

_SAFECAST_URL = "https://api.safecast.org/measurements.json"
# Rough, widely-used approximation for consumer Geiger tubes (e.g. SBM-20).
# Actual conversion depends on the specific tube - this is indicative only.
_CPM_TO_USVH = 0.0057


class StralingCommand(BaseCommand):
    """Reports an indicative radiation level near a place (Safecast data)."""

    name = "straling"
    keywords = ["straling"]
    description = "Indicatief stralingsniveau nabij een plaats (usage: straling <plaats>)"
    category = "general"
    requires_internet = True

    short_description = "Indicatief stralingsniveau"
    usage = "straling <plaats>"
    examples = ["straling Diest", "straling Eindhoven"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.straling_enabled = self.get_config_value(
            "Straling_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.straling_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return (
            "Indicatief stralingsniveau nabij een plaats, op basis van Safecast "
            "burgerwetenschap-sensoren (geen officiële meting)."
        )

    async def _query_safecast(self, lat: float, lon: float, distance_km: int) -> list[dict]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "distance": distance_km,
            "unit": "cpm",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _SAFECAST_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [m for m in data if m.get("unit") == "cpm" and m.get("value") is not None]

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip()
            if content.lower().startswith("straling"):
                content = content[len("straling"):].strip()

            if not content:
                return await self.send_response(message, self.translate("commands.straling.usage"))

            lat, lon, _ = await geocode_city(self.bot, content)
            if lat is None or lon is None:
                return await self.send_response(message, self.translate("commands.straling.not_found", place=content))

            measurements = await self._query_safecast(lat, lon, 25)
            radius_used = 25
            if not measurements:
                measurements = await self._query_safecast(lat, lon, 100)
                radius_used = 100

            if not measurements:
                return await self.send_response(
                    message,
                    self.translate("commands.straling.no_data", radius=radius_used, place=content),
                )

            # Most recent few readings, median to reduce impact of outliers.
            measurements.sort(key=lambda m: m.get("captured_at", ""), reverse=True)
            recent = measurements[:5]
            cpm_values = [float(m["value"]) for m in recent]
            cpm_median = median(cpm_values)
            usvh = cpm_median * _CPM_TO_USVH

            newest_ts = recent[0].get("captured_at")
            age_str = ""
            if newest_ts:
                try:
                    ts = datetime.fromisoformat(newest_ts.replace("Z", "+00:00"))
                    age_str = self.translate("commands.straling.age_suffix", date=ts.strftime("%Y-%m-%d"))
                except ValueError:
                    pass

            response = self.translate(
                "commands.straling.result",
                place=content, radius=radius_used, n=len(recent), age=age_str,
                usvh=f"{usvh:.3f}", cpm=f"{cpm_median:.0f}",
            )
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing straling command: {e}")
            return await self.send_response(message, self.translate("commands.straling.error", error=str(e)))
