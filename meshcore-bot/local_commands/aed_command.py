#!/usr/bin/env python3
"""
'aed' command for the MeshCore Bot.
Nearest AED (defibrillator) locations near a place, from OpenStreetMap's
Overpass API (tag emergency=defibrillator) - free, no key, same kind of
source as the bot's own OSM map tiles.

Asked in a channel, the answer goes as a direct message to the one who asked (card: "Answer by direct message",
on by default); when that DM cannot be sent it comes in the channel.
"""

from typing import Any

import aiohttp

from ..mesh_community import REPLY_BY_DM_FIELD, reply_private
from ..models import MeshMessage
from ..utils import calculate_distance, geocode_city
from .base_command import BaseCommand

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_RADIUS_M = 2000


class AedCommand(BaseCommand):
    """Shows the nearest AEDs to a place, from OpenStreetMap."""

    name = "aed"
    keywords = ["aed"]
    description = "Dichtstbijzijnde AED's nabij een plaats (usage: aed <plaats>)"
    category = "general"
    requires_internet = True

    short_description = "Dichtstbijzijnde AED's"
    usage = "aed <plaats>"
    examples = ["aed Utrecht", "aed Heerlen"]

    settings_schema = [REPLY_BY_DM_FIELD]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.aed_enabled = self.get_config_value(
            "Aed_Command", "enabled", fallback=True, value_type="bool"
        )
        self.reply_by_dm = self.get_config_value("Aed_Command", "reply_by_dm", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.aed_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Dichtstbijzijnde AED's (defibrillatoren) nabij een plaats, uit OpenStreetMap."

    async def _query_overpass(self, lat: float, lon: float) -> list[dict]:
        query = (
            f"[out:json][timeout:15];"
            f'node["emergency"="defibrillator"](around:{_RADIUS_M},{lat},{lon});'
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
            if content.lower().startswith("aed"):
                content = content[len("aed"):].strip()

            if not content:
                return await reply_private(self, message, self.translate("commands.aed.usage"))

            lat, lon, _ = await geocode_city(self.bot, content)
            if lat is None or lon is None:
                return await reply_private(self, message, self.translate("commands.aed.not_found", place=content))

            elements = await self._query_overpass(lat, lon)
            if not elements:
                return await reply_private(
                    self, message,
                    self.translate("commands.aed.no_data", radius=_RADIUS_M // 1000, place=content),
                )

            for el in elements:
                el["_distance_km"] = calculate_distance(lat, lon, el["lat"], el["lon"])
            elements.sort(key=lambda e: e["_distance_km"])

            lines = [self.translate("commands.aed.header", place=content)]
            for el in elements[:3]:
                tags = el.get("tags", {})
                name = tags.get("name") or tags.get("operator") or "AED"
                dist_m = int(el["_distance_km"] * 1000)
                lines.append(self.translate("commands.aed.line", name=name, distance=dist_m))

            response = "\n".join(lines)
            return await reply_private(self, message, response)
        except Exception as e:
            self.logger.error(f"Error executing aed command: {e}")
            return await reply_private(self, message, self.translate("commands.aed.error", error=str(e)))
