#!/usr/bin/env python3
"""
'storing' command for the MeshCore Bot.
Telecom outage status (KPN/Vodafone/Ziggo/Odido/T-Mobile) scraped from
storingradar.com - a community aggregator, NOT an official provider status
page. No official free API exists for this (checked KPN's developer portal
and Enexis-style outage APIs; providers only expose this through their own
JS-rendered apps with no documented backend). Explicitly flagged as
unofficial in the response text, since there's no way to verify accuracy.
"""

import re
from typing import Any, Optional

import aiohttp

from ..models import MeshMessage
from .base_command import BaseCommand

_BASE_URL = "https://storingradar.com/storing/{provider}"
_PROVIDERS = {
    "kpn": "KPN",
    "vodafone": "Vodafone",
    "ziggo": "Ziggo",
    "odido": "Odido",
    "t-mobile": "T-Mobile",
}
_STATUS_RE = re.compile(
    r'role="alert".{0,400}?<p class="[^"]*text-(?P<color>\w+)-600[^"]*">(?P<status>[^<]+)</p>',
    re.DOTALL,
)


class StoringCommand(BaseCommand):
    """Shows telecom outage status per provider (unofficial, storingradar.com)."""

    name = "storing"
    keywords = ["storing"]
    description = "Storingsstatus telecomprovider (usage: storing <kpn|vodafone|ziggo|odido|t-mobile>)"
    category = "general"
    requires_internet = True

    short_description = "Storingsstatus telecomprovider"
    usage = "storing <kpn|vodafone|ziggo|odido|t-mobile>"
    examples = ["storing kpn", "storing ziggo"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.storing_enabled = self.get_config_value(
            "Storing_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.storing_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        providers = ", ".join(_PROVIDERS)
        return (
            f"Storingsstatus van een telecomprovider ({providers}), via de "
            "community-site storingradar.com - geen officiële providerbron."
        )

    async def _fetch_status(self, session: aiohttp.ClientSession, provider: str) -> Optional[re.Match]:
        url = _BASE_URL.format(provider=provider)
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()
        return _STATUS_RE.search(html)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip().lower()
            if content.startswith("storing"):
                content = content[len("storing"):].strip()

            if content not in _PROVIDERS:
                providers = ", ".join(_PROVIDERS)
                return await self.send_response(message, self.translate("commands.storing.usage", providers=providers))

            async with aiohttp.ClientSession() as session:
                match = await self._fetch_status(session, content)

            if not match:
                return await self.send_response(
                    message, self.translate("commands.storing.fetch_error", provider=_PROVIDERS[content])
                )

            status_text = match.group("status").strip()
            response = self.translate(
                "commands.storing.result", provider=_PROVIDERS[content], status=status_text
            )
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing storing command: {e}")
            return await self.send_response(message, self.translate("commands.storing.error", error=str(e)))
