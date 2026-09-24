#!/usr/bin/env python3
"""
'karma' command for the MeshCore Bot: thank someone with a point.

  karma <naam>     give <naam> one point (for help, a good tip, a relay)
  karma            your own points
  karma top        (or: topkarma) the top 5, all time

Rules, so it stays a thank-you and not a game of farming points:
- only for a name the bot has heard in the last 30 days (upstream's message_stats, and the archive of
  modules/mesh_archive.py for the days upstream no longer keeps), and not for yourself or a bot;
- the same giver can give the same person one point per day, and at most [Karma_Command] per_day points per day.
People are recognised by the name they use on the mesh (a channel message carries nothing else).
"""

import time
from datetime import timedelta
from typing import Any

from ..mesh_archive import ensure_archive, sync
from ..mesh_community import is_bot_name, local_day, pack_lines, split_args, table_exists, without_bots
from ..models import MeshMessage
from .base_command import BaseCommand

TOP = {"top", "ranglijst"}
RECENT_DAYS = 30


class KarmaCommand(BaseCommand):
    """Give someone a thank-you point; karma top shows the ranking."""

    name = "karma"
    keywords = ["karma", "topkarma"]
    description = "Iemand bedanken met een punt (karma <naam>), karma = jouw punten, karma top = ranglijst"
    category = "fun"

    short_description = "Iemand bedanken met een karmapunt"
    usage = "karma [<naam>|top]"
    examples = ["karma", "karma Piet", "karma top", "topkarma"]

    settings_schema = [
        {"key": "per_day", "label": "Points one person may give per day", "type": "int", "default": 3, "min": 1, "max": 20,
         "help": "Also: the same person can get at most one point per day from the same giver."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.karma_enabled = self.get_config_value("Karma_Command", "enabled", fallback=True, value_type="bool")
        self.per_day = max(1, int(self.get_config_value("Karma_Command", "per_day", fallback=3, value_type="int") or 3))
        self._ready = False

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.karma_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.karma.help", per_day=self.per_day)

    def _db(self):
        if not self._ready:
            ensure_archive(self.bot.db_manager)
            self._ready = True
        return self.bot.db_manager.connection()

    def _known_name(self, conn, name: str) -> str:
        """The name as the bot saw it lately, or '' when unknown."""
        if table_exists(conn, "message_stats"):
            row = conn.execute(
                "SELECT sender_id FROM message_stats WHERE LOWER(sender_id) = LOWER(?) AND timestamp >= ? ORDER BY timestamp DESC LIMIT 1",
                (name, int(time.time()) - RECENT_DAYS * 86400)).fetchone()
            if row:
                return row[0]
        since = (local_day(self.bot) - timedelta(days=RECENT_DAYS)).isoformat()
        row = conn.execute("SELECT name FROM community_activity WHERE LOWER(name) = LOWER(?) AND day >= ? ORDER BY day DESC LIMIT 1",
                           (name, since)).fetchone()
        return row[0] if row else ""

    def points(self, name: str) -> int:
        with self._db() as conn:
            return conn.execute("SELECT COUNT(*) FROM community_karma WHERE LOWER(receiver) = LOWER(?)", (name,)).fetchone()[0]

    def give(self, giver: str, target: str, now_ts: float = None) -> str:
        now_ts = time.time() if now_ts is None else now_ts
        today = local_day(self.bot, now_ts).isoformat()
        target = target.strip().lstrip("@").strip("[]").strip()
        if not giver:
            return self.translate("commands.karma.no_name")
        if target.lower() == giver.lower():
            return self.translate("commands.karma.self")
        if is_bot_name(self.bot, target):
            return self.translate("commands.karma.bot")
        sync(self.bot)
        with self._db() as conn:
            known = self._known_name(conn, target)
            if not known:
                return self.translate("commands.karma.unknown", name=target, days=RECENT_DAYS)
            given_today = conn.execute("SELECT COUNT(*) FROM community_karma WHERE LOWER(giver)=LOWER(?) AND day=?", (giver, today)).fetchone()[0]
            if given_today >= self.per_day:
                return self.translate("commands.karma.limit", per_day=self.per_day)
            if conn.execute("SELECT 1 FROM community_karma WHERE LOWER(giver)=LOWER(?) AND LOWER(receiver)=LOWER(?) AND day=?",
                            (giver, known, today)).fetchone():
                return self.translate("commands.karma.already", name=known)
            conn.execute("INSERT INTO community_karma (giver, receiver, day, ts) VALUES (?,?,?,?)", (giver, known, today, int(now_ts)))
            conn.commit()
            total = conn.execute("SELECT COUNT(*) FROM community_karma WHERE LOWER(receiver)=LOWER(?)", (known,)).fetchone()[0]
        return self.translate("commands.karma.given", name=known, giver=giver, total=total)

    def top(self, max_bytes: int) -> list:
        with self._db() as conn:
            rows = conn.execute("SELECT receiver, COUNT(*) AS n FROM community_karma GROUP BY LOWER(receiver) ORDER BY n DESC, MIN(ts) LIMIT 40").fetchall()
        rows = without_bots(self.bot, rows, 5)
        if not rows:
            return [self.translate("commands.karma.top_empty")]
        return pack_lines(self.translate("commands.karma.top_header"), [f"{i}. {n} {p}" for i, (n, p) in enumerate(rows, 1)], max_bytes)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            args = split_args(self, message)
            first = (message.content or "").strip().lstrip("!/").split(" ", 1)[0].lower()
            if first == "topkarma" or args.lower() in TOP:
                chunks = self.top(self.get_max_message_length(message))
                return await (self.send_response(message, chunks[0]) if len(chunks) == 1 else self.send_response_chunked(message, chunks[:2]))
            if not args:
                me = message.sender_id or "?"
                return await self.send_response(message, self.translate("commands.karma.own", name=me, total=self.points(me)))
            return await self.send_response(message, self.give(message.sender_id or "", args))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing karma command: {e}")
            return await self.send_response(message, self.translate("commands.karma.error", error=str(e)))
