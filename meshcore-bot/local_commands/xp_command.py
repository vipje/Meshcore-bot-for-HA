#!/usr/bin/env python3
"""
'xp' command for the MeshCore Bot: Mesh RPG, where just using the mesh earns experience, levels and a title.

  xp                 your level, title and XP (and how much to the next level)
  xp <naam>          the same for someone else
  xp top [week]      the top 5 by XP, of all time or only what was earned this week

XP (see modules/mesh_archive.py): 1 per message (max 20 a day), 2 per bot command (max 10 a day), 5 per check-in,
10 per karma point received, 5 per hop of your best DX (up to 10 hops, so at most 50). The daily caps keep it a reward for taking part, not for
flooding the channel. Level L needs 25 x L x (L+1) XP. Bots are left out of the ranking.
"""

import time
from typing import Any

from ..mesh_archive import known_names, sync, week_start_day, xp_of
from ..mesh_community import pack_lines, split_args, without_bots
from ..models import MeshMessage
from .base_command import BaseCommand

TOP = {"top", "ranglijst"}
WEEK = {"week", "w"}


class XpCommand(BaseCommand):
    """Mesh RPG: XP, level and title for taking part on the mesh."""

    name = "xp"
    keywords = ["xp", "level"]
    description = "Mesh RPG: je XP, level en titel (xp, xp <naam>, xp top [week])"
    category = "games"

    short_description = "Mesh RPG: XP, level en titel"
    usage = "xp [<naam>|top [week]]"
    examples = ["xp", "xp Piet", "xp top", "xp top week"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.xp_enabled = self.get_config_value("Xp_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.xp_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.xp.help")

    def person(self, name: str) -> str:
        info = xp_of(self.bot, name)
        if not info["xp"]:
            return self.translate("commands.xp.none", name=name)
        return self.translate("commands.xp.reply", name=name, level=info["level"], xp=info["xp"],
                              title=self.translate(f"commands.xp.title.{info['title']}"), left=info["next"] - info["xp"])

    def top(self, week: bool, max_bytes: int, now_ts: float = None) -> list:
        since = week_start_day(self.bot, now_ts) if week else None
        scores = [(n, xp_of(self.bot, n, since)["xp"]) for n in known_names(self.bot, since)]
        scores.sort(key=lambda r: (-r[1], r[0].lower()))
        rows = without_bots(self.bot, [r for r in scores if r[1] > 0], 5)
        label = self.translate("commands.xp.week" if week else "commands.xp.ever")
        if not rows:
            return [self.translate("commands.xp.top_empty", label=label)]
        return pack_lines(self.translate("commands.xp.top_header", label=label), [f"{i}. {n} {x}" for i, (n, x) in enumerate(rows, 1)], max_bytes)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            sync(self.bot)
            args = split_args(self, message)
            words = args.lower().split()
            if words and words[0] in TOP:
                chunks = self.top(len(words) > 1 and words[1] in WEEK, self.get_max_message_length(message), time.time())
                return await (self.send_response(message, chunks[0]) if len(chunks) == 1 else self.send_response_chunked(message, chunks[:2]))
            return await self.send_response(message, self.person(args or message.sender_id or "?"))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing xp command: {e}")
            return await self.send_response(message, self.translate("commands.xp.error", error=str(e)))
