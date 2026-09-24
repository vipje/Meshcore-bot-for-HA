#!/usr/bin/env python3
"""
'tanken' command for the MeshCore Bot.
Today's official CBS landelijk-gemiddelde pompprijzen (Euro95/diesel/LPG) -
free, no key, official government source (CBS OData table 80416ned).

NOT a "nearest station" lookup: no free real-time per-station price API
exists (checked Tankje.nl/ANWB/GRID - all app-only, no public API; CBS is
the only clean official source, and it's a national daily average).
"""

from datetime import datetime, timedelta
from typing import Any

import aiohttp

from ..models import MeshMessage
from .base_command import BaseCommand

_URL = "https://opendata.cbs.nl/ODataApi/OData/80416ned/TypedDataSet"


class TankenCommand(BaseCommand):
    """Shows today's official CBS national-average fuel pump prices."""

    name = "tanken"
    keywords = ["tanken"]
    description = "Landelijk gemiddelde brandstofprijzen vandaag (CBS)"
    category = "general"
    requires_internet = True

    short_description = "Landelijke brandstofprijzen (CBS)"
    usage = "tanken"
    examples = ["tanken"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.tanken_enabled = self.get_config_value(
            "Tanken_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.tanken_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Landelijk gemiddelde pompprijzen van vandaag/gisteren (CBS, geen 'dichtstbijzijnde pomp')."

    async def execute(self, message: MeshMessage) -> bool:
        try:
            since = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
            params = {"$filter": f"Perioden ge '{since}'"}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    _URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return await self.send_response(
                            message, self.translate("commands.tanken.fetch_error")
                        )
                    data = await resp.json()

            rows = data.get("value") or []
            if not rows:
                return await self.send_response(message, self.translate("commands.tanken.no_data"))

            latest = max(rows, key=lambda r: r.get("Perioden", ""))
            date_str = latest.get("Perioden", "")
            date_fmt = f"{date_str[6:8]}-{date_str[4:6]}-{date_str[:4]}" if len(date_str) == 8 else date_str

            euro95 = latest.get("BenzineEuro95_1")
            diesel = latest.get("Diesel_2")
            lpg = latest.get("Lpg_3")

            response = self.translate(
                "commands.tanken.result",
                date=date_fmt, euro95=f"{euro95:.3f}", diesel=f"{diesel:.3f}", lpg=f"{lpg:.3f}",
            )
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing tanken command: {e}")
            return await self.send_response(message, self.translate("commands.tanken.error", error=str(e)))
