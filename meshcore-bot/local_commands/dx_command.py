#!/usr/bin/env python3
"""
'dx' command for the MeshCore Bot: DX Jacht, the record for the message that came in over the most hops.

  dx               records of this week, this month and ever (most hops, who, when)
  dx top [week|maand|ooit]   top 5 people by their best hop count in that window (default: week)
  dx ik            your own best of the week, the month and ever
  dx <naam>        the same for someone else

Upstream's stats keep every channel message that arrived over repeaters in path_stats (sender name, hop count,
path, time), but only for 7 days. The best of each person per day is copied into our own archive
(modules/mesh_archive.py, table community_dx) by the Community service and before every dx reply, so records of
the month and of all time stay. Needs the bot's statistics ([Stats_Command] track_all_messages). Bots are left
out of the rankings (Bots page rules).
"""

import time
from typing import Any, Optional

from ..mesh_archive import dx_best, month_start_day, sync, week_start_day
from ..mesh_community import local_now, pack_lines, split_args, without_bots
from ..models import MeshMessage
from .base_command import BaseCommand

WEEK = {"week", "w"}
MONTH = {"maand", "month", "monat", "mois", "m"}
EVER = {"ooit", "ever", "alles", "all", "immer", "toujours"}
TOP = {"top", "ranglijst", "rank"}
ME = {"ik", "me", "mij", "mijn", "ich", "moi"}


class DxCommand(BaseCommand):
    """DX Jacht: hop records per week, month and ever."""

    name = "dx"
    keywords = ["dx"]
    description = "DX Jacht: records voor het bericht met de meeste hops (dx, dx top, dx ik, dx <naam>)"
    category = "fun"

    short_description = "DX Jacht: hop-records per week, maand en ooit"
    usage = "dx [top [week|maand|ooit]|ik|<naam>]"
    examples = ["dx", "dx top", "dx top maand", "dx ik"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.dx_enabled = self.get_config_value("Dx_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.dx_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.dx.help")

    # ------------------------------------------------------------------ data
    def _best(self, since_day: Optional[str], name: Optional[str] = None, limit: int = 1) -> list:
        """[(name, hops, ts)] best first; one row per person (their best), bots left out unless a name is asked."""
        rows = dx_best(self.bot, since_day, name=name)
        if name:
            return rows[:limit]
        return without_bots(self.bot, rows, limit)

    def _when(self, ts: int) -> str:
        return local_now(self.bot, ts).strftime("%d-%m")

    def _window(self, word: str) -> tuple:
        now = time.time()
        if word in MONTH:
            return month_start_day(self.bot, now), self.translate("commands.dx.month")
        if word in EVER:
            return None, self.translate("commands.dx.ever")
        return week_start_day(self.bot, now), self.translate("commands.dx.week")

    # ------------------------------------------------------------------ replies
    def _records(self) -> str:
        parts = []
        for word in ("week", "maand", "ooit"):
            since, label = self._window(word)
            best = self._best(since)
            if best:
                who, hops, ts = best[0]
                parts.append(self.translate("commands.dx.record", label=label, name=who, hops=hops, date=self._when(ts)))
            else:
                parts.append(self.translate("commands.dx.record_none", label=label))
        return self.translate("commands.dx.records_header") + " " + " | ".join(parts)

    def _top(self, word: str, max_bytes: int) -> list:
        since, label = self._window(word)
        rows = self._best(since, limit=5)
        if not rows:
            return [self.translate("commands.dx.no_data", label=label)]
        items = [f"{i}. {who} {hops}" for i, (who, hops, _ts) in enumerate(rows, 1)]
        return pack_lines(self.translate("commands.dx.top_header", label=label), items, max_bytes)

    def _person(self, name: str) -> str:
        parts = []
        for word in ("week", "maand", "ooit"):
            since, label = self._window(word)
            best = self._best(since, name=name)
            parts.append(f"{label} {best[0][1]}" if best else f"{label} -")
        if all(p.endswith(" -") for p in parts):
            return self.translate("commands.dx.person_none", name=name)
        return self.translate("commands.dx.person", name=name, records=" | ".join(parts))

    async def execute(self, message: MeshMessage) -> bool:
        try:
            sync(self.bot)
            args = split_args(self, message)
            words = args.lower().split()
            max_bytes = self.get_max_message_length(message)
            if not words:
                text = self._records()
            elif words[0] in TOP:
                chunks = self._top(words[1] if len(words) > 1 else "week", max_bytes)
                if len(chunks) > 1:
                    return await self.send_response_chunked(message, chunks[:2])
                text = chunks[0]
            elif words[0] in ME:
                text = self._person(message.sender_id or "?")
            else:
                text = self._person(args.strip())
            return await self.send_response(message, text)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing dx command: {e}")
            return await self.send_response(message, self.translate("commands.dx.error", error=str(e)))
