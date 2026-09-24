#!/usr/bin/env python3
"""
'uptime' command for the MeshCore Bot.
Reports how long the bot has been running since its last (re)start.
"""

import time
from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand


class UptimeCommand(BaseCommand):
    """Reports bot process uptime since last restart."""

    name = "uptime"
    keywords = ["uptime"]
    description = "Hoe lang de bot al draait sinds de laatste herstart"
    category = "general"

    short_description = "Bot-uptime sinds laatste herstart"
    usage = "uptime"
    examples = ["uptime"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.uptime_enabled = self.get_config_value(
            "Uptime_Command", "enabled", fallback=True, value_type="bool"
        )
        # Set once, when the plugin is loaded at bot startup - this is the
        # closest we get to "process start time" without touching core.py.
        self._started_at = time.time()

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.uptime_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Toont hoe lang de bot al draait sinds de laatste herstart."

    def _format_duration(self, seconds: float) -> str:
        seconds = int(seconds)
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, _ = divmod(seconds, 60)

        parts = []
        if days:
            parts.append(self.translate("commands.uptime.days", n=days))
        if hours:
            parts.append(self.translate("commands.uptime.hours", n=hours))
        if minutes or not parts:
            parts.append(self.translate("commands.uptime.minutes", n=minutes))
        return " ".join(parts)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            elapsed = time.time() - self._started_at
            duration = self._format_duration(elapsed)
            started_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(self._started_at))
            response = self.translate("commands.uptime.result", duration=duration, started=started_str)
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing uptime command: {e}")
            return await self.send_response(message, self.translate("commands.uptime.error", error=str(e)))
