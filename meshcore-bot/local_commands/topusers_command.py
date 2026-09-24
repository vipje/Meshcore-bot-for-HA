#!/usr/bin/env python3
"""
'topu' command for the MeshCore Bot.
Short alias for the top-5 busiest users. Defaults to the last 24 hours;
an optional day count picks a wider window, e.g. 'topu 7' for 7 days.

Mirrors the webviewer dashboard's own "Busiest users" panel (modules/
web_viewer/dashboard_stats.py, DashboardStats.read_top(), kind="users"):
counts from message_stats (every message seen on a monitored channel), not
command_stats. An earlier version of this command counted command_stats
instead - a top-3 of the built-in `stats messages` subcommand, which despite
its name also only counts bot-command invocations - so it showed "who uses
the bot most" rather than "who talks the most", and gave different numbers
than the dashboard panel of the same name.

Other bots are left out automatically (same rules as the Bots page: robot emoji or the word bot in
the name, plus the hand-made lists there; switch: [Topusers_Command] hide_bots). Names listed under
[Topusers_Command] exclude (comma separated, not case sensitive) are never shown either, for example
a room server that shows up with your own messages.
"""

import time
from typing import Any

from ..mesh_community import without_bots
from ..models import MeshMessage
from ..top_list_chunking import chunk_top_list, parse_days_arg, window_label
from .base_command import BaseCommand


class TopUsersCommand(BaseCommand):
    """Shows the top 5 busiest users (by message count) over a given window."""

    name = "topusers"
    keywords = ["topu"]
    description = "Top 5 actiefste gebruikers (optioneel: topu <dagen>, standaard 24u)"
    category = "analytics"

    short_description = "Top 5 actiefste gebruikers (24u, of 'topu N' voor N dagen)"
    usage = "topu [dagen]"
    examples = ["topu", "topu 7"]

    # Shown as a field on this plugin's card on the dashboard's Plugins page.
    settings_schema = [
        {
            "key": "hide_bots", "label": "Leave out bots", "type": "bool", "default": True,
            "help": ("Other bots (robot emoji or the word bot in the name, and the names marked as bot on the "
                     "Bots page) and this bot itself are never listed."),
        },
        {
            "key": "exclude", "label": "Never show these names", "type": "list", "default": "",
            "help": ("Names the topu command never lists, comma-separated, not case sensitive "
                     "(for example a room server that shows up with your own messages, or another bot)."),
        },
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        raw = self.get_config_value("Topusers_Command", "exclude", fallback="")
        self.excluded = [n.strip().lower() for n in str(raw).split(",") if n.strip()]
        self.hide_bots = self.get_config_value("Topusers_Command", "hide_bots", fallback=True, value_type="bool")

    async def execute(self, message: MeshMessage) -> bool:
        try:
            days = parse_days_arg(message.content, "topu")
            window_ago = int(time.time()) - (days * 24 * 60 * 60)
            # Names that must never be shown (filtered in SQL so the list still has 5 entries).
            skip = ""
            params: list = [window_ago]
            if self.excluded:
                skip = "AND LOWER(sender_id) NOT IN (" + ",".join("?" * len(self.excluded)) + ")"
                params += self.excluded
            with self.bot.db_manager.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT sender_id, COUNT(*) as count
                    FROM message_stats
                    WHERE timestamp >= ? {skip}
                    GROUP BY sender_id
                    ORDER BY count DESC
                    LIMIT ?
                    """,
                    params + [50 if self.hide_bots else 5],
                )
                top_users = cursor.fetchall()
            # Bots are recognised by name (Bots page rules), which SQL cannot do: fetch more, keep the first 5 people.
            top_users = without_bots(self.bot, top_users, 5) if self.hide_bots else top_users[:5]

            label = window_label(days)
            if not top_users:
                return await self.send_response(
                    message, self.translate("commands.topusers.no_data", label=label)
                )

            lines = [f"{i}. {user}: {count}" for i, (user, count) in enumerate(top_users, 1)]

            chunks = chunk_top_list(
                self.translate("commands.topusers.header", label=label), lines, self.get_max_message_length(message)
            )
            if len(chunks) == 1:
                return await self.send_response(message, chunks[0])
            return await self.send_response_chunked(message, chunks)
        except Exception as e:
            self.logger.error(f"Error executing topu command: {e}")
            return await self.send_response(message, self.translate("commands.topusers.error", error=str(e)))
