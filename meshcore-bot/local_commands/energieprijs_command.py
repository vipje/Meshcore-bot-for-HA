#!/usr/bin/env python3
"""
'energieprijs' command for the MeshCore Bot.
Current dynamic electricity price (EnergyZero's public API - free, no key,
widely used in the Dutch home-automation community).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from ..models import MeshMessage
from .base_command import BaseCommand

_URL = "https://api.energyzero.nl/v1/energyprices"


class EnergieprijsCommand(BaseCommand):
    """Shows the current dynamic electricity price and today's range (EnergyZero)."""

    name = "energieprijs"
    keywords = ["energieprijs"]
    description = "Actuele dynamische stroomprijs (EnergyZero)"
    category = "general"
    requires_internet = True

    short_description = "Actuele dynamische stroomprijs"
    usage = "energieprijs"
    examples = ["energieprijs"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.energieprijs_enabled = self.get_config_value(
            "Energieprijs_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.energieprijs_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Actuele dynamische stroomprijs (incl. btw), plus het laagste/hoogste uurtarief van vandaag."

    async def execute(self, message: MeshMessage) -> bool:
        try:
            now = datetime.now(timezone.utc)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1) - timedelta(milliseconds=1)
            params = {
                "fromDate": day_start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "tillDate": day_end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "interval": 4,
                "usageType": 1,
                "inclBtw": "true",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    _URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return await self.send_response(
                            message, self.translate("commands.energieprijs.fetch_error")
                        )
                    data = await resp.json()

            prices = data.get("Prices") or []
            if not prices:
                return await self.send_response(message, self.translate("commands.energieprijs.no_data"))

            current = None
            for p in prices:
                try:
                    ts = datetime.fromisoformat(p["readingDate"].replace("Z", "+00:00"))
                except (ValueError, KeyError):
                    continue
                if ts <= now and (current is None or ts > current["_ts"]):
                    p["_ts"] = ts
                    current = p

            values = [p["price"] for p in prices if "price" in p]
            low = min(values)
            high = max(values)

            cur_str = f"{current['price']:.3f}" if current else "?"
            response = self.translate(
                "commands.energieprijs.result", current=cur_str, low=f"{low:.3f}", high=f"{high:.3f}"
            )
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing energieprijs command: {e}")
            return await self.send_response(message, self.translate("commands.energieprijs.error", error=str(e)))
