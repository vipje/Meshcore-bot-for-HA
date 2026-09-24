#!/usr/bin/env python3
"""
'herinner' command for the MeshCore Bot: a personal reminder, delivered back to you as a direct message.

  herinner 30m <tekst>      in 30 minutes (also: 2u / 2h, 1d)
  herinner 18:30 <tekst>    at 18:30 (today, or tomorrow when that time has passed)
  herinner lijst            your open reminders       herinner weg <nr>     cancel one

Direct message only: the reminder goes to your public key, which only a DM carries, so nobody can set reminders for
someone else. At most 3 open reminders per person, at most 7 days ahead. The Reminders service (Plugins ->
Reminders) delivers them; it keeps them in the database, so a restart of the bot loses nothing.
"""

import time
from typing import Any

from ..mesh_community import ensure_tables, fit_bytes, local_now, parse_when, split_args
from ..models import MeshMessage
from .base_command import BaseCommand

LIST = {"lijst", "list", "liste"}
REMOVE = {"weg", "verwijder", "del", "delete", "remove"}
MAX_OPEN = 3
MAX_AHEAD_S = 7 * 86400
MAX_TEXT_BYTES = 100


class HerinnerCommand(BaseCommand):
    """Personal reminder by direct message."""

    name = "herinner"
    keywords = ["herinner", "remind"]
    description = "Persoonlijke herinnering via DM (herinner 30m <tekst>, herinner 18:30 <tekst>, herinner lijst)"
    category = "general"
    requires_dm = True

    short_description = "Persoonlijke herinnering via DM"
    usage = "herinner <30m|2u|1d|HH:MM> <tekst>"
    examples = ["herinner 30m pizza uit de oven", "herinner 18:30 antenne binnenhalen", "herinner lijst", "herinner weg 2"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.herinner_enabled = self.get_config_value("Herinner_Command", "enabled", fallback=True, value_type="bool")
        self._ready = False

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.herinner_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.herinner.help", max=MAX_OPEN)

    def _db(self):
        if not self._ready:
            ensure_tables(self.bot.db_manager)
            self._ready = True
        return self.bot.db_manager.connection()

    def _at(self, ts: int, now_ts: float) -> str:
        at, now = local_now(self.bot, ts), local_now(self.bot, now_ts)
        return at.strftime("%H:%M") if at.date() == now.date() else at.strftime("%d-%m %H:%M")

    def _open(self, conn, pubkey: str) -> list:
        return conn.execute("SELECT id, text, due_at FROM community_reminders WHERE pubkey=? AND done=0 ORDER BY due_at",
                            (pubkey,)).fetchall()

    def handle(self, pubkey: str, name: str, args: str, now_ts: float = None) -> str:
        now_ts = time.time() if now_ts is None else now_ts
        if not pubkey:
            return self.translate("commands.herinner.no_key")
        pubkey = pubkey.lower()
        words = args.split()
        with self._db() as conn:
            if not words:
                return self.translate("commands.herinner.usage")
            if words[0].lower() in LIST:
                rows = self._open(conn, pubkey)
                if not rows:
                    return self.translate("commands.herinner.none")
                items = " | ".join(f"#{i} {self._at(d, now_ts)} {fit_bytes(t, 30)}" for i, t, d in rows)
                return self.translate("commands.herinner.list", items=items)
            if words[0].lower() in REMOVE and len(words) == 2 and words[1].lstrip("#").isdigit():
                n = int(words[1].lstrip("#"))
                gone = conn.execute("DELETE FROM community_reminders WHERE id=? AND pubkey=? AND done=0", (n, pubkey)).rowcount
                conn.commit()
                return self.translate("commands.herinner.removed" if gone else "commands.herinner.not_found", id=n)
            due = parse_when(words[0], self.bot, now_ts)
            text = " ".join(words[1:]).strip()
            if due is None or not text:
                return self.translate("commands.herinner.usage")
            if due - now_ts > MAX_AHEAD_S:
                return self.translate("commands.herinner.too_far")
            if due - now_ts < 60:
                return self.translate("commands.herinner.too_soon")
            if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
                return self.translate("commands.herinner.too_long", max=MAX_TEXT_BYTES)
            if len(self._open(conn, pubkey)) >= MAX_OPEN:
                return self.translate("commands.herinner.max_open", max=MAX_OPEN)
            cur = conn.execute("INSERT INTO community_reminders (pubkey, name, text, due_at, created_at) VALUES (?,?,?,?,?)",
                               (pubkey, name or "", text, int(due), int(now_ts)))
            conn.commit()
        service_on = "reminders" in (getattr(self.bot, "services", None) or {})
        key = "commands.herinner.set" if service_on else "commands.herinner.set_service_off"
        return self.translate(key, id=cur.lastrowid, at=self._at(int(due), now_ts))

    async def execute(self, message: MeshMessage) -> bool:
        try:
            return await self.send_response(message, self.handle(message.sender_pubkey or "", message.sender_id or "",
                                                                 split_args(self, message)))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing herinner command: {e}")
            return await self.send_response(message, self.translate("commands.herinner.error", error=str(e)))
