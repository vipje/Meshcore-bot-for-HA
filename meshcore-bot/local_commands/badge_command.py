#!/usr/bin/env python3
"""
'badge' command for the MeshCore Bot: the milestones someone reached on the mesh (part of Mesh RPG).

  badge            your badges          badge <naam>      someone else's

Badges (modules/mesh_archive.py, BADGES): 100 and 1000 messages, active on 30 and 100 days, a message over 3 and
over 6 hops, a check-in streak of 7 and 30 days, 10 karma points, level 5 and level 10. Computed from what the bot
archived, nothing to claim or to lose.
"""

from typing import Any

from ..mesh_archive import BADGES, badges_of, sync
from ..mesh_community import fit_bytes, split_args
from ..models import MeshMessage
from .base_command import BaseCommand


class BadgeCommand(BaseCommand):
    """Milestones on the mesh (Mesh RPG)."""

    name = "badge"
    keywords = ["badge", "badges"]
    description = "Mesh RPG: behaalde mijlpalen (badge, badge <naam>)"
    category = "games"

    short_description = "Mesh RPG: behaalde mijlpalen"
    usage = "badge [<naam>]"
    examples = ["badge", "badge Piet"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.badge_enabled = self.get_config_value("Badge_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.badge_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.badge.help")

    def build(self, name: str, max_bytes: int) -> str:
        earned = badges_of(self.bot, name)
        if not earned:
            return self.translate("commands.badge.none", name=name)
        names = ", ".join(self.translate(f"commands.badge.name.{key}") for key in earned)
        return fit_bytes(self.translate("commands.badge.reply", name=name, n=len(earned), total=len(BADGES), badges=names), max_bytes)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            sync(self.bot)
            name = split_args(self, message) or message.sender_id or "?"
            return await self.send_response(message, self.build(name, self.get_max_message_length(message)))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing badge command: {e}")
            return await self.send_response(message, self.translate("commands.badge.error", error=str(e)))
