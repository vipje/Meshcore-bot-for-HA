#!/usr/bin/env python3
"""
'laadpaal' command for the MeshCore Bot.
Nearest EV charging stations near a place, from OpenStreetMap's Overpass API
(tag amenity=charging_station) - free, no key. Same approach as the 'aed'
command; deliberately not OpenChargeMap, which needs a registered API key.
"""

from typing import Any

import aiohttp

from ..models import MeshMessage
from ..utils import calculate_distance, geocode_city
from .base_command import BaseCommand

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_RADIUS_M = 5000


class LaadpaalCommand(BaseCommand):
    """Shows the nearest EV charging stations to a place, from OpenStreetMap."""

    name = "laadpaal"
    keywords = ["laadpaal"]
    description = "Dichtstbijzijnde laadpalen nabij een plaats (usage: laadpaal <plaats>)"
    category = "general"
    requires_internet = True

    short_description = "Dichtstbijzijnde laadpalen"
    usage = "laadpaal <plaats>"
    examples = ["laadpaal Utrecht", "laadpaal Sittard"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.laadpaal_enabled = self.get_config_value(
            "Laadpaal_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.laadpaal_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Dichtstbijzijnde EV-laadpalen nabij een plaats, uit OpenStreetMap."

    async def _query_overpass(self, lat: float, lon: float) -> list[dict]:
        query = (
            f"[out:json][timeout:15];"
            f'node["amenity"="charging_station"](around:{_RADIUS_M},{lat},{lon});'
            f"out body;"
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _OVERPASS_URL, data={"data": query}, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("elements", [])

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip()
            if content.lower().startswith("laadpaal"):
                content = content[len("laadpaal"):].strip()

            if not content:
                return await self.send_response(message, self.translate("commands.laadpaal.usage"))

            lat, lon, _ = await geocode_city(self.bot, content)
            if lat is None or lon is None:
                return await self.send_response(message, self.translate("commands.laadpaal.not_found", place=content))

            elements = await self._query_overpass(lat, lon)
            if not elements:
                return await self.send_response(
                    message,
                    self.translate("commands.laadpaal.no_data", radius=_RADIUS_M // 1000, place=content),
                )

            for el in elements:
                el["_distance_km"] = calculate_distance(lat, lon, el["lat"], el["lon"])
            elements.sort(key=lambda e: e["_distance_km"])

            lines = [self.translate("commands.laadpaal.header", place=content)]
            for el in elements[:3]:
                tags = el.get("tags", {})
                name = tags.get("operator") or tags.get("name") or self.translate("commands.laadpaal.generic_name")
                sockets = tags.get("capacity")
                dist_m = int(el["_distance_km"] * 1000)
                extra = f" ({sockets}x)" if sockets else ""
                lines.append(self.translate("commands.laadpaal.line", name=name, extra=extra, distance=dist_m))

            response = "\n".join(lines)
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing laadpaal command: {e}")
            return await self.send_response(message, self.translate("commands.laadpaal.error", error=str(e)))
