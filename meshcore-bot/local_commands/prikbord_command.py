#!/usr/bin/env python3
"""
'prikbord' command for the MeshCore Bot: short notes that stay readable for a few days.

  prikbord                 the newest notes (number, name, text, days left)
  prikbord <tekst>         pin a note, e.g. "prikbord pomp te leen, Weert"
  prikbord <nummer>        one note in full
  prikbord weg <nummer>    remove your own note

Limits (card: Plugins -> prikbord): a note lives [Prikbord_Command] days days (default 7), at most max_per_person
notes per person at a time (default 2), at most 20 on the board. A note is at most 90 bytes, so the list of the
newest notes still fits a message or two. Notes belong to the name that pinned them.
"""

import math
import re
import time
from typing import Any

from ..mesh_community import ensure_tables, fit_bytes, pack_lines, split_args
from ..models import MeshMessage
from .base_command import BaseCommand

REMOVE = {"weg", "verwijder", "del", "delete", "remove"}
MAX_TEXT_BYTES = 90
MAX_ON_BOARD = 20


class PrikbordCommand(BaseCommand):
    """A notice board: pin a short note for a few days, read the newest notes."""

    name = "prikbord"
    keywords = ["prikbord"]
    description = "Prikbord: korte berichten die een paar dagen blijven staan (prikbord, prikbord <tekst>, prikbord weg <nr>)"
    category = "general"

    short_description = "Prikbord met korte berichten (een paar dagen)"
    usage = "prikbord [<tekst>|<nr>|weg <nr>]"
    examples = ["prikbord", "prikbord pomp te leen, Weert", "prikbord 3", "prikbord weg 3"]

    settings_schema = [
        {"key": "days", "label": "Keep a note for", "type": "int", "default": 7, "min": 1, "max": 30, "unit": "days"},
        {"key": "max_per_person", "label": "Notes per person at a time", "type": "int", "default": 2, "min": 1, "max": 5},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.board_enabled = self.get_config_value("Prikbord_Command", "enabled", fallback=True, value_type="bool")
        self.days = max(1, int(self.get_config_value("Prikbord_Command", "days", fallback=7, value_type="int") or 7))
        self.per_person = max(1, int(self.get_config_value("Prikbord_Command", "max_per_person", fallback=2, value_type="int") or 2))
        self._ready = False

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.board_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.prikbord.help", days=self.days)

    def _db(self):
        if not self._ready:
            ensure_tables(self.bot.db_manager)
            self._ready = True
        return self.bot.db_manager.connection()

    def _active(self, conn, now_ts: float) -> list:
        return conn.execute("SELECT id, name, text, expires_at FROM community_board WHERE expires_at > ? ORDER BY id DESC",
                            (int(now_ts),)).fetchall()

    def _left(self, expires_at: int, now_ts: float) -> str:
        days = math.ceil((expires_at - now_ts) / 86400)
        return self.translate("commands.prikbord.days_left", n=max(1, days))

    def pin(self, name: str, text: str, now_ts: float = None) -> str:
        now_ts = time.time() if now_ts is None else now_ts
        text = re.sub(r"\s+", " ", text).strip()
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            return self.translate("commands.prikbord.too_long", max=MAX_TEXT_BYTES)
        with self._db() as conn:
            conn.execute("DELETE FROM community_board WHERE expires_at <= ?", (int(now_ts),))
            active = self._active(conn, now_ts)
            if sum(1 for r in active if r[1].lower() == name.lower()) >= self.per_person:
                return self.translate("commands.prikbord.per_person", max=self.per_person)
            if len(active) >= MAX_ON_BOARD:
                return self.translate("commands.prikbord.full", max=MAX_ON_BOARD)
            cur = conn.execute("INSERT INTO community_board (name, text, created_at, expires_at) VALUES (?,?,?,?)",
                               (name, text, int(now_ts), int(now_ts + self.days * 86400)))
            conn.commit()
            return self.translate("commands.prikbord.pinned", id=cur.lastrowid, days=self.days)

    def remove(self, name: str, number: int, now_ts: float = None) -> str:
        now_ts = time.time() if now_ts is None else now_ts
        with self._db() as conn:
            row = conn.execute("SELECT name FROM community_board WHERE id=? AND expires_at > ?", (number, int(now_ts))).fetchone()
            if not row:
                return self.translate("commands.prikbord.not_found", id=number)
            if row[0].lower() != (name or "").lower():
                return self.translate("commands.prikbord.not_yours", id=number)
            conn.execute("DELETE FROM community_board WHERE id=?", (number,))
            conn.commit()
        return self.translate("commands.prikbord.removed", id=number)

    def show(self, number: int, now_ts: float = None) -> str:
        now_ts = time.time() if now_ts is None else now_ts
        with self._db() as conn:
            row = conn.execute("SELECT id, name, text, expires_at FROM community_board WHERE id=? AND expires_at > ?",
                               (number, int(now_ts))).fetchone()
        if not row:
            return self.translate("commands.prikbord.not_found", id=number)
        return f"#{row[0]} {row[1]}: {row[2]} ({self._left(row[3], now_ts)})"

    def listing(self, max_bytes: int, now_ts: float = None) -> list:
        now_ts = time.time() if now_ts is None else now_ts
        with self._db() as conn:
            active = self._active(conn, now_ts)
        if not active:
            return [self.translate("commands.prikbord.empty")]
        items = [fit_bytes(f"#{i} {n}: {t}", 60) for i, n, t, _e in active[:6]]
        header = self.translate("commands.prikbord.header", n=len(active))
        return pack_lines(header, items, max_bytes)[:2]

    async def execute(self, message: MeshMessage) -> bool:
        try:
            args = split_args(self, message)
            words = args.split()
            if not words:
                chunks = self.listing(self.get_max_message_length(message))
                return await (self.send_response(message, chunks[0]) if len(chunks) == 1 else self.send_response_chunked(message, chunks))
            if len(words) == 1 and words[0].lstrip("#").isdigit():
                return await self.send_response(message, self.show(int(words[0].lstrip("#"))))
            if words[0].lower() in REMOVE and len(words) == 2 and words[1].lstrip("#").isdigit():
                return await self.send_response(message, self.remove(message.sender_id or "", int(words[1].lstrip("#"))))
            if not message.sender_id:
                return await self.send_response(message, self.translate("commands.prikbord.no_name"))
            return await self.send_response(message, self.pin(message.sender_id, args))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing prikbord command: {e}")
            return await self.send_response(message, self.translate("commands.prikbord.error", error=str(e)))
