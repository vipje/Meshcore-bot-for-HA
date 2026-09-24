#!/usr/bin/env python3
"""
'topr' command for the MeshCore Bot.
Short alias for the top-3 busiest repeaters (kept at 3, not 5 like topu/topc,
so it reliably fits one mesh message even with long repeater names). Defaults
to the last 24 hours; an optional day count picks a wider window, e.g.
'topr 7' for 7 days.

Mirrors the exact query behind the webviewer dashboard's own "Busiest
repeaters" panel (modules/web_viewer/dashboard_stats.py, DashboardStats.
read_top(), kind="repeaters") rather than a fresh guess at the schema: an
earlier version of this command filtered on ``role = 'Repeater'`` (as
written by repeater_manager.py for new adverts) and got different numbers
than the dashboard, which filters on the lowercase values that are actually
present in complete_contact_tracking.role for existing rows. The day-count
argument mirrors the dashboard's own window math too: `since = today -
(days - 1)`.
"""

from datetime import date, timedelta
from typing import Any

from ..models import MeshMessage
from ..top_list_chunking import chunk_top_list, parse_days_arg, window_label
from .base_command import BaseCommand


class TopRepeatersCommand(BaseCommand):
    """Shows the top 3 busiest repeaters (by advert count) over a given window."""

    name = "toprepeaters"
    keywords = ["topr"]
    description = "Top 3 drukste repeaters (optioneel: topr <dagen>, standaard 24u)"
    category = "analytics"

    short_description = "Top 3 drukste repeaters (24u, of 'topr N' voor N dagen)"
    usage = "topr [dagen]"
    examples = ["topr", "topr 7"]

    def __init__(self, bot: Any):
        super().__init__(bot)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            days = parse_days_arg(message.content, "topr")
            # daily_stats rows are per calendar day, not a rolling clock, so
            # a 1-day window ("24u") is "today" (since = today). SUM handles
            # wider windows spanning multiple daily_stats rows per repeater.
            since = date.today() - timedelta(days=days - 1)
            with self.bot.db_manager.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT c.name, c.public_key, SUM(ds.advert_count) AS adverts
                    FROM daily_stats ds
                    JOIN complete_contact_tracking c ON c.public_key = ds.public_key
                    WHERE ds.date >= ? AND c.role IN ('repeater', 'roomserver')
                    GROUP BY ds.public_key
                    ORDER BY adverts DESC
                    LIMIT 3
                    """,
                    (since,),
                )
                top_repeaters = cursor.fetchall()

            label = window_label(days)
            if not top_repeaters:
                return await self.send_response(
                    message, self.translate("commands.toprepeaters.no_data", label=label)
                )

            lines = [
                f"{i}. {name or (public_key or '')[:12]}: {count}"
                for i, (name, public_key, count) in enumerate(top_repeaters, 1)
            ]

            chunks = chunk_top_list(
                self.translate("commands.toprepeaters.header", label=label), lines, self.get_max_message_length(message)
            )
            if len(chunks) == 1:
                return await self.send_response(message, chunks[0])
            return await self.send_response_chunked(message, chunks)
        except Exception as e:
            self.logger.error(f"Error executing topr command: {e}")
            return await self.send_response(message, self.translate("commands.toprepeaters.error", error=str(e)))
