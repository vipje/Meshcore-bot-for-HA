#!/usr/bin/env python3
"""
'ov' command for the MeshCore Bot.
Next public-transport departures from a stop, via OVapi.nl (KV78Turbo REST,
free for light/non-scraping use - no key). Uses plain HTTP: the TLS
certificate on v0.ovapi.nl currently doesn't match its own hostname (CN is
de.ovapi.nl), so HTTPS fails cert validation; the service itself works fine
over HTTP.
"""

import time
from typing import Any, Optional

import aiohttp

from ..models import MeshMessage
from .base_command import BaseCommand

_STOP_LIST_URL = "http://v0.ovapi.nl/stopareacode"
_DEPARTURES_URL = "http://v0.ovapi.nl/stopareacode/{code}"
_STOP_LIST_CACHE_SECONDS = 24 * 60 * 60


class OvCommand(BaseCommand):
    """Shows the next few departures from a public-transport stop (OVapi.nl)."""

    name = "ov"
    keywords = ["ov"]
    description = "Eerstvolgende OV-vertrektijden bij een halte (usage: ov <plaats/halte>)"
    category = "general"
    requires_internet = True

    short_description = "OV-vertrektijden bij een halte"
    usage = "ov <plaats/halte>"
    examples = ["ov Utrecht", "ov Heerlen Station"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.ov_enabled = self.get_config_value(
            "Ov_Command", "enabled", fallback=True, value_type="bool"
        )
        self._stop_list_cache: Optional[dict] = None
        self._stop_list_cached_at: float = 0.0

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.ov_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Eerstvolgende OV-vertrektijden bij een halte, op naam van plaats en/of halte (OVapi.nl)."

    async def _get_stop_list(self, session: aiohttp.ClientSession) -> dict:
        now = time.time()
        if self._stop_list_cache is not None and (now - self._stop_list_cached_at) < _STOP_LIST_CACHE_SECONDS:
            return self._stop_list_cache
        async with session.get(_STOP_LIST_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            resp.raise_for_status()
            data = await resp.json()
        self._stop_list_cache = data
        self._stop_list_cached_at = now
        return data

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip()
            if content.lower().startswith("ov"):
                content = content[len("ov"):].strip()

            if not content:
                return await self.send_response(message, self.translate("commands.ov.usage"))

            needle = content.lower()
            async with aiohttp.ClientSession() as session:
                stops = await self._get_stop_list(session)

                matches = [
                    (code, info)
                    for code, info in stops.items()
                    if needle in (info.get("TimingPointTown", "") + " " + info.get("TimingPointName", "")).lower()
                ]
                if not matches:
                    return await self.send_response(message, self.translate("commands.ov.no_stop", query=content))

                matches = matches[:3]
                passes: list[dict] = []
                for code, info in matches:
                    async with session.get(
                        _DEPARTURES_URL.format(code=code), timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                    for tp in (data.get(code) or {}).values():
                        for p in (tp.get("Passes") or {}).values():
                            p["_stop_name"] = f"{info.get('TimingPointTown', '')} {info.get('TimingPointName', '')}".strip()
                            passes.append(p)

            if not passes:
                return await self.send_response(message, self.translate("commands.ov.no_departures", query=content))

            passes.sort(key=lambda p: p.get("ExpectedDepartureTime") or p.get("TargetDepartureTime") or "")

            lines = [self.translate("commands.ov.header", query=content)]
            for p in passes[:5]:
                dep = p.get("ExpectedDepartureTime") or p.get("TargetDepartureTime") or ""
                time_str = dep[11:16] if len(dep) >= 16 else "?"
                line_nr = p.get("LinePublicNumber", "?")
                dest = p.get("DestinationName50", "?")
                lines.append(self.translate(
                    "commands.ov.line", time=time_str, line=line_nr, dest=dest, stop=p["_stop_name"]
                ))

            response = "\n".join(lines)
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing ov command: {e}")
            return await self.send_response(message, self.translate("commands.ov.error", error=str(e)))
