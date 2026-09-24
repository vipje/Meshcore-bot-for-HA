#!/usr/bin/env python3
"""
'beving' command for the MeshCore Bot.
Recent earthquakes in/near the Netherlands, from KNMI's public RSS feed
(free, no key - the JSON dataset on the KNMI Data Platform needs a key,
this RSS feed doesn't).
"""

import re
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp

from ..models import MeshMessage
from .base_command import BaseCommand

_RSS_URL = "https://rdsa.knmi.nl/abcws/event/query?format=rss&limit=30"
# The feed also carries non-earthquake seismo-acoustic events (e.g. sonic
# booms); those get "M = -" (no magnitude) instead of a number.
_DESC_RE = re.compile(
    r"M\s*=\s*(?P<mag>[\d.]+).*?Plaats\s*=\s*(?P<place>[^,]+)"
)


class BevingCommand(BaseCommand):
    """Shows the most recent earthquakes in/near the Netherlands (KNMI)."""

    name = "beving"
    keywords = ["beving"]
    description = "Recente aardbevingen in/rond Nederland (KNMI)"
    category = "general"
    requires_internet = True

    short_description = "Recente aardbevingen (KNMI)"
    usage = "beving"
    examples = ["beving"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.beving_enabled = self.get_config_value(
            "Beving_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.beving_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Top 3 recente aardbevingen in/rond Nederland, uit de KNMI-seismologiefeed."

    async def execute(self, message: MeshMessage) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    _RSS_URL, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return await self.send_response(
                            message, self.translate("commands.beving.fetch_error")
                        )
                    body = await resp.text()

            root = ET.fromstring(body)
            quakes = []
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                desc = (item.findtext("description") or "").strip()
                m = _DESC_RE.search(desc)
                if not m:
                    continue  # no magnitude -> not an earthquake (e.g. sonic boom)
                date_part = title.split(",")[0].strip()
                quakes.append(
                    f"{date_part}: M={m.group('mag')} {m.group('place').strip()}"
                )
                if len(quakes) >= 3:
                    break

            if not quakes:
                return await self.send_response(
                    message, self.translate("commands.beving.no_data")
                )

            response = self.translate("commands.beving.header") + "\n" + "\n".join(quakes)
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing beving command: {e}")
            return await self.send_response(message, self.translate("commands.beving.error", error=str(e)))
