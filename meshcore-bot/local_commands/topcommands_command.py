#!/usr/bin/env python3
"""
'topc' command for the MeshCore Bot.
Short alias showing the top 5 most-used bot commands. Defaults to the last
24 hours; an optional day count picks a wider window, e.g. 'topc 7' for 7 days.
"""

import time
from typing import Any

from ..models import MeshMessage
from ..top_list_chunking import chunk_top_list, parse_days_arg, window_label
from .base_command import BaseCommand


class TopCommandsCommand(BaseCommand):
    """Shows the top 5 most-used bot commands over a given window."""

    name = "topcommands"
    keywords = ["topc"]
    description = "Top 5 meest gebruikte commando's (optioneel: topc <dagen>, standaard 24u)"
    category = "analytics"

    short_description = "Top 5 commando's (24u, of 'topc N' voor N dagen)"
    usage = "topc [dagen]"
    examples = ["topc", "topc 7"]

    def __init__(self, bot: Any):
        super().__init__(bot)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            days = parse_days_arg(message.content, "topc")
            window_ago = int(time.time()) - (days * 24 * 60 * 60)
            with self.bot.db_manager.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT command_name, COUNT(*) as count
                    FROM command_stats
                    WHERE timestamp >= ?
                    GROUP BY command_name
                    ORDER BY count DESC
                    LIMIT 5
                    """,
                    (window_ago,),
                )
                top_commands = cursor.fetchall()

            label = window_label(days)
            if not top_commands:
                return await self.send_response(
                    message, self.translate("commands.topcommands.no_data", label=label)
                )

            lines = [f"{i}. {name}: {count}" for i, (name, count) in enumerate(top_commands, 1)]

            chunks = chunk_top_list(
                self.translate("commands.topcommands.header", label=label), lines, self.get_max_message_length(message)
            )
            if len(chunks) == 1:
                return await self.send_response(message, chunks[0])
            return await self.send_response_chunked(message, chunks)
        except Exception as e:
            self.logger.error(f"Error executing topc command: {e}")
            return await self.send_response(message, self.translate("commands.topcommands.error", error=str(e)))
