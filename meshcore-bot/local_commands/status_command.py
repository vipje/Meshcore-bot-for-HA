#!/usr/bin/env python3
"""
'status' command for the MeshCore Bot (admin only).

Shows uptime, radio state, contact usage, command/error counters and the most
recent problem, on request. Works with or without notifications switched on.
"""

import time
from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand


class StatusCommand(BaseCommand):
    """Bot health at a glance."""

    name = "status"
    keywords = ["status"]
    description = "Toestand van de bot: uptime, radio, contacten, fouten (admin)"
    category = "admin"

    short_description = "Botstatus (admin)"
    usage = "status"
    examples = ["status"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.status_enabled = self.get_config_value(
            "Status_Command", "enabled", fallback=True, value_type="bool"
        )

    def requires_admin_access(self) -> bool:
        return True

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.status_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "status toont uptime, radio, contacten en de laatste fout (admin)."

    async def execute(self, message: MeshMessage) -> bool:
        service = getattr(self.bot, "services", {}).get("notify")
        if service is None:
            return await self.send_response(message, self.translate("commands.status.no_service"))
        try:
            from modules.service_plugins.notify_service import format_duration, fit

            await service.refresh_contact_limit()
            c = service.counters
            contacts = getattr(getattr(self.bot, "meshcore", None), "contacts", None) or {}
            limit = getattr(getattr(self.bot, "repeater_manager", None), "contact_limit", 0)
            parts = [
                self.translate("commands.status.up", duration=format_duration(time.time() - service.started_at)),
                self.translate("commands.status.radio", state=service.radio_state()),
                self.translate("commands.status.contacts", n=len(contacts))
                + (f"/{limit}" if limit else ""),
                self.translate(
                    "commands.status.counters", commands=c["commands"], errors=c["errors"], warnings=c["warnings"]
                ),
            ]
            if service.issues:
                ts, _category, text = service.issues[-1]
                age = format_duration(time.time() - ts)
                parts.append(self.translate("commands.status.last_issue", age=age, text=text))
            else:
                parts.append(self.translate("commands.status.no_issues"))
            return await self.send_response(
                message, fit(self.translate("commands.status.header") + " " + " | ".join(parts), 150)
            )
        except Exception as e:
            self.logger.error(f"Error executing status command: {e}")
            return await self.send_response(message, self.translate("commands.status.error", error=str(e)))
