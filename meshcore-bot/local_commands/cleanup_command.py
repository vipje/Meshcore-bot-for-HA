#!/usr/bin/env python3
"""
'cleanup' command for the MeshCore Bot (admin only).

  cleanup            show what a contact cleanup would remove (nothing is changed)
  cleanup now        run it
  cleanup stale      show which contacts have been silent for too long
  cleanup stale now  remove them

Uses the ContactCleanup service; starred contacts, favourites, the room server,
admins and recently active contacts are never removed, and removed contacts stay
on the dashboard map.
"""

from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand


class CleanupCommand(BaseCommand):
    """Trim the radio's contact list on demand."""

    name = "cleanup"
    keywords = ["cleanup", "opschonen"]
    description = "Contactlijst van de radio opschonen (admin)"
    category = "admin"

    short_description = "Contacten opschonen (admin)"
    usage = "cleanup [stale] [now]"
    examples = ["cleanup", "cleanup now", "cleanup stale"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.cleanup_enabled = self.get_config_value(
            "Cleanup_Command", "enabled", fallback=True, value_type="bool"
        )

    def requires_admin_access(self) -> bool:
        return True

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.cleanup_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "cleanup toont wat er opgeschoond zou worden, cleanup now voert het uit; cleanup stale voor stille contacten (admin)."

    async def execute(self, message: MeshMessage) -> bool:
        service = getattr(self.bot, "services", {}).get("contactcleanup")
        if service is None:
            return await self.send_response(message, self.translate("commands.cleanup.no_service"))
        try:
            words = (message.content or "").lower().split()
            run_now = "now" in words or "nu" in words
            if "stale" in words or "oud" in words:
                result = await service.run_stale(dry_run=not run_now, reason="command")
                if result["planned"] == 0:
                    info = result["info"]
                    text = self.translate(
                        "commands.cleanup.stale_none",
                        repeater_days=result["repeater_days"], other_days=result["other_days"],
                        oldest=info["oldest_days"], protected=info["protected"], unknown=info["unknown_age"],
                    )
                elif result["dry_run"]:
                    shown = ", ".join(result["names"][:3])
                    more = f" +{len(result['names']) - 3}" if len(result["names"]) > 3 else ""
                    text = self.translate(
                        "commands.cleanup.stale_preview", planned=result["planned"], shown=shown, more=more
                    )
                else:
                    text = self.translate(
                        "commands.cleanup.stale_done",
                        removed=result["removed"], planned=result["planned"], after=result.get("after", "?"),
                    )
                return await self.send_response(message, text)
            result = await service.run(dry_run=not run_now, reason="command")
            if result["planned"] == 0:
                info = result["info"]
                text = self.translate(
                    "commands.cleanup.none",
                    before=result["before"], target=result["target"], protected=info["protected"],
                    recent=info["recent"], keep_days=service.keep_days, oldest=info["oldest_days"],
                )
            elif result["dry_run"]:
                shown = ", ".join(result["names"][:3])
                more = f" +{len(result['names']) - 3}" if len(result["names"]) > 3 else ""
                text = self.translate(
                    "commands.cleanup.preview",
                    before=result["before"], target=result["target"], planned=result["planned"],
                    shown=shown, more=more,
                )
            else:
                text = self.translate(
                    "commands.cleanup.done",
                    removed=result["removed"], planned=result["planned"], after=result.get("after", "?"),
                )
            return await self.send_response(message, text)
        except Exception as e:
            self.logger.error(f"Error executing cleanup command: {e}")
            return await self.send_response(message, self.translate("commands.cleanup.error", error=str(e)))
