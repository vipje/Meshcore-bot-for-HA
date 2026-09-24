#!/usr/bin/env python3
"""
'checkin' command for the MeshCore Bot: a daily "I'm here" with a streak counter.

  checkin          (or: meld) check in for today: your streak, your record and how many checked in today
  checkin top      the longest current streaks (top 5)

One check-in per name per day; the day is the bot's local day (Europe/Amsterdam unless [Bot] timezone says
otherwise). A streak is the number of days in a row up to today or yesterday: missing one day starts it again.
"""

import time
from datetime import timedelta
from typing import Any

from ..mesh_community import ensure_tables, local_day, pack_lines, split_args, streaks, without_bots
from ..models import MeshMessage
from .base_command import BaseCommand

TOP = {"top", "ranglijst"}


class CheckinCommand(BaseCommand):
    """Daily check-in with a streak counter."""

    name = "checkin"
    keywords = ["checkin", "meld", "inchecken"]
    description = "Dagelijks inchecken met een reeks-teller (checkin, checkin top)"
    category = "fun"

    short_description = "Dagelijks inchecken, met reeks"
    usage = "checkin [top]"
    examples = ["checkin", "meld", "checkin top"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.checkin_enabled = self.get_config_value("Checkin_Command", "enabled", fallback=True, value_type="bool")
        self._ready = False

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.checkin_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.checkin.help")

    def _db(self):
        if not self._ready:
            ensure_tables(self.bot.db_manager)
            self._ready = True
        return self.bot.db_manager.connection()

    def check_in(self, name: str, now_ts: float = None) -> str:
        now_ts = time.time() if now_ts is None else now_ts
        today = local_day(self.bot, now_ts)
        with self._db() as conn:
            new = conn.execute("INSERT OR IGNORE INTO community_checkin (name, day, ts) VALUES (?,?,?)",
                               (name, today.isoformat(), int(now_ts))).rowcount
            conn.commit()
            days = [r[0] for r in conn.execute("SELECT day FROM community_checkin WHERE LOWER(name)=LOWER(?)", (name,)).fetchall()]
            count = conn.execute("SELECT COUNT(*) FROM community_checkin WHERE day=?", (today.isoformat(),)).fetchone()[0]
        current, best = streaks(days, today)
        key = "commands.checkin.done" if new else "commands.checkin.again"
        return self.translate(key, name=name, streak=current, best=best, today=count, total=len(days))

    def top(self, max_bytes: int, now_ts: float = None) -> list:
        today = local_day(self.bot, now_ts)
        with self._db() as conn:
            rows = conn.execute("SELECT name, day FROM community_checkin WHERE day >= ?", ((today - timedelta(days=400)).isoformat(),)).fetchall()
        per: dict = {}
        for name, day in rows:
            per.setdefault(name.lower(), [name, []])[1].append(day)
        ranking = sorted(((n, streaks(ds, today)[0]) for n, ds in per.values()), key=lambda r: (-r[1], r[0].lower()))
        ranking = without_bots(self.bot, [r for r in ranking if r[1] > 0], 5)
        if not ranking:
            return [self.translate("commands.checkin.top_empty")]
        return pack_lines(self.translate("commands.checkin.top_header"), [f"{i}. {n} {s}" for i, (n, s) in enumerate(ranking, 1)], max_bytes)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            if split_args(self, message).lower() in TOP:
                chunks = self.top(self.get_max_message_length(message))
                return await (self.send_response(message, chunks[0]) if len(chunks) == 1 else self.send_response_chunked(message, chunks[:2]))
            if not message.sender_id:
                return await self.send_response(message, self.translate("commands.checkin.no_name"))
            return await self.send_response(message, self.check_in(message.sender_id))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing checkin command: {e}")
            return await self.send_response(message, self.translate("commands.checkin.error", error=str(e)))
