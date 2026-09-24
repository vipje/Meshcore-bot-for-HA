#!/usr/bin/env python3
"""
'wegwerk' command for the MeshCore Bot.
Nearby road works / lane/speed management, from NDW's national open-data
DATEX II feed (free, no key). See local_shared/ndw_situations.py for the
shared fetch/parse logic (also used by file_command.py).
"""

from typing import Any

import aiohttp

from ..models import MeshMessage
from ..ndw_situations import get_situations
from ..utils import calculate_distance, geocode_city
from .base_command import BaseCommand

_RADIUS_KM = 20
_TYPES = {
    "RoadOrCarriagewayOrLaneManagement",
    "SpeedManagement",
    "ReroutingManagement",
    "GeneralNetworkManagement",
}

class WegwerkCommand(BaseCommand):
    """Shows nearby road works / lane closures / speed limits (NDW)."""

    name = "wegwerk"
    keywords = ["wegwerk"]
    description = "Wegwerkzaamheden nabij een plaats (usage: wegwerk <plaats>)"
    category = "general"
    requires_internet = True

    short_description = "Wegwerkzaamheden nabij een plaats"
    usage = "wegwerk <plaats>"
    examples = ["wegwerk Heerlen"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.wegwerk_enabled = self.get_config_value(
            "Wegwerk_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.wegwerk_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Wegwerkzaamheden/rijstrookmaatregelen binnen 20km van een plaats (NDW open data)."

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip()
            if content.lower().startswith("wegwerk"):
                content = content[len("wegwerk"):].strip()

            if not content:
                return await self.send_response(message, self.translate("commands.wegwerk.usage"))

            lat, lon, _ = await geocode_city(self.bot, content)
            if lat is None or lon is None:
                return await self.send_response(message, self.translate("commands.wegwerk.not_found", place=content))

            async with aiohttp.ClientSession() as session:
                situations = await get_situations(session)

            nearby = []
            for s in situations:
                if s["type"] not in _TYPES:
                    continue
                dist = calculate_distance(lat, lon, s["lat"], s["lon"])
                if dist <= _RADIUS_KM:
                    s["_distance_km"] = dist
                    nearby.append(s)

            if not nearby:
                return await self.send_response(
                    message, self.translate("commands.wegwerk.no_data", radius=_RADIUS_KM, place=content)
                )

            nearby.sort(key=lambda s: s["_distance_km"])
            lines = [self.translate("commands.wegwerk.header", place=content)]
            for s in nearby[:5]:
                label = self.translate(f"commands.wegwerk.type.{s['type']}")
                dist_str = f"{s['_distance_km']:.0f}km"
                lines.append(self.translate("commands.wegwerk.line", label=label, distance=dist_str))

            response = "\n".join(lines)
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing wegwerk command: {e}")
            return await self.send_response(message, self.translate("commands.wegwerk.error", error=str(e)))
