#!/usr/bin/env python3
"""
'waterstand' command for the MeshCore Bot.
Latest Maas water level (cm t.o.v. NAP) at a known Rijkswaterstaat gauge,
via RWS's new Waterwebservices (the old waterwebservices.rijkswaterstaat.nl
host now redirects to a migration notice; this uses the replacement host,
ddapi20-waterwebservices.rijkswaterstaat.nl).

Only a small curated set of Maas gauges near this bot's region (Zuid-
Limburg) is supported for now - the full RWS location catalogue is a
~1.5MB, non-trivial-to-navigate JSON (OphalenCatalogus on METADATASERVICES),
and most entries aren't active WATHTE (water height) series. Extend
_STATIONS below with more `METADATASERVICES/OphalenCatalogus` lookups if
more locations are wanted later.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from ..models import MeshMessage
from .base_command import BaseCommand

_URL = (
    "https://ddapi20-waterwebservices.rijkswaterstaat.nl/"
    "ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen"
)
# name (lowercase, as typed) -> RWS Locatie.Code
_STATIONS = {
    "elsloo": "elsloo.maas",
    "grave": "grave.beneden",
}
_DEFAULT_STATION = "elsloo"


class WaterstandCommand(BaseCommand):
    """Shows the latest Maas water level at a known gauge (Rijkswaterstaat)."""

    name = "waterstand"
    keywords = ["waterstand"]
    description = "Actuele waterstand Maas bij een meetpunt (usage: waterstand [elsloo|grave])"
    category = "general"
    requires_internet = True

    short_description = "Actuele Maas-waterstand"
    usage = "waterstand [elsloo|grave]"
    examples = ["waterstand", "waterstand grave"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.waterstand_enabled = self.get_config_value(
            "Waterstand_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.waterstand_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        stations = ", ".join(_STATIONS)
        return f"Actuele Maas-waterstand (cm t.o.v. NAP) bij een meetpunt ({stations})."

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip().lower()
            if content.startswith("waterstand"):
                content = content[len("waterstand"):].strip()

            station_name = content if content in _STATIONS else _DEFAULT_STATION
            location_code = _STATIONS[station_name]

            now = datetime.now(timezone.utc)
            begin = now - timedelta(hours=3)
            body = {
                "AquoPlusWaarnemingMetadata": {
                    "AquoMetadata": {
                        "Eenheid": {"Code": "cm"},
                        "Grootheid": {"Code": "WATHTE"},
                        "Hoedanigheid": {"Code": "NAP"},
                    }
                },
                "Locatie": {"Code": location_code},
                "Periode": {
                    "Begindatumtijd": begin.strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
                    "Einddatumtijd": now.strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
                },
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    _URL, json=body, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 204:
                        return await self.send_response(
                            message, self.translate("commands.waterstand.no_data", station=station_name)
                        )
                    if resp.status != 200:
                        return await self.send_response(
                            message, self.translate("commands.waterstand.fetch_error")
                        )
                    data = await resp.json()

            metingen = []
            for w in data.get("WaarnemingenLijst", []):
                metingen.extend(w.get("MetingenLijst", []))
            if not metingen:
                return await self.send_response(
                    message, self.translate("commands.waterstand.no_data", station=station_name)
                )

            metingen.sort(key=lambda m: m.get("Tijdstip", ""))
            latest = metingen[-1]
            waarde_cm = latest.get("Meetwaarde", {}).get("Waarde_Numeriek")
            tijdstip = latest.get("Tijdstip", "")

            if waarde_cm is None:
                return await self.send_response(
                    message, self.translate("commands.waterstand.no_valid", station=station_name)
                )

            waarde_m = waarde_cm / 100
            time_str = tijdstip[11:16] if len(tijdstip) >= 16 else tijdstip
            response = self.translate(
                "commands.waterstand.result", station=station_name, value=f"{waarde_m:.2f}", time=time_str
            )
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing waterstand command: {e}")
            return await self.send_response(message, self.translate("commands.waterstand.error", error=str(e)))
