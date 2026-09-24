#!/usr/bin/env python3
"""
'feestdag' command for the MeshCore Bot.
Reports today's (or tomorrow's) official public holidays for NL + BE, via
the free Nager.Date API (no key required).
"""

import time
from datetime import date, timedelta
from typing import Any

import aiohttp

from ..models import MeshMessage
from .base_command import BaseCommand

_API_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
_COUNTRIES = ("NL", "BE")
_CACHE_TTL_SECONDS = 24 * 60 * 60


class FeestdagCommand(BaseCommand):
    """Reports today's/tomorrow's official BE/NL public holidays."""

    name = "feestdag"
    keywords = ["feestdag", "vandaag"]
    description = "Feestdagen NL/BE (usage: feestdag, feestdag morgen)"
    category = "general"
    requires_internet = True

    short_description = "Feestdagen NL/BE vandaag/morgen"
    usage = "feestdag [morgen]"
    examples = ["feestdag", "feestdag morgen"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.feestdag_enabled = self.get_config_value(
            "Feestdag_Command", "enabled", fallback=True, value_type="bool"
        )
        # (year -> {country: [holiday dicts]}) cache, refreshed once a day.
        self._cache: dict[int, dict[str, list[dict]]] = {}
        self._cache_fetched_at: dict[int, float] = {}

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.feestdag_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Toont officiële feestdagen in NL en BE voor vandaag (of 'feestdag morgen')."

    async def _get_holidays_for_year(self, year: int) -> dict[str, list[dict]]:
        cached_at = self._cache_fetched_at.get(year, 0)
        if year in self._cache and (time.time() - cached_at) < _CACHE_TTL_SECONDS:
            return self._cache[year]

        result: dict[str, list[dict]] = {}
        async with aiohttp.ClientSession() as session:
            for country in _COUNTRIES:
                url = _API_URL.format(year=year, country=country)
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            result[country] = await resp.json()
                        else:
                            result[country] = []
                except Exception as e:
                    self.logger.warning(f"feestdag: kon {country} {year} niet ophalen: {e}")
                    result[country] = []

        self._cache[year] = result
        self._cache_fetched_at[year] = time.time()
        return result

    @staticmethod
    def _holidays_on(holidays_by_country: dict[str, list[dict]], target: date) -> list[tuple[str, str]]:
        target_str = target.isoformat()
        found = []
        for country, holidays in holidays_by_country.items():
            for holiday in holidays:
                if holiday.get("date") == target_str:
                    found.append((country, holiday.get("localName") or holiday.get("name") or "?"))
        return found

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip().lower()
            target = date.today()
            label = self.translate("commands.feestdag.today")
            if "morgen" in content:
                target = target + timedelta(days=1)
                label = self.translate("commands.feestdag.tomorrow")

            holidays_by_country = await self._get_holidays_for_year(target.year)
            found = self._holidays_on(holidays_by_country, target)

            date_str = target.strftime("%d-%m-%Y")
            if not found:
                response = self.translate("commands.feestdag.none", label=label, date=date_str)
            else:
                # Dedupe identical holiday names shared by both countries.
                by_name: dict[str, list[str]] = {}
                for country, name in found:
                    by_name.setdefault(name, []).append(country)
                lines = [self.translate("commands.feestdag.header", label=label, date=date_str)]
                for name, countries in by_name.items():
                    lines.append(f"{name} ({'/'.join(countries)})")
                response = " | ".join(lines)

            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing feestdag command: {e}")
            return await self.send_response(message, self.translate("commands.feestdag.error", error=str(e)))
