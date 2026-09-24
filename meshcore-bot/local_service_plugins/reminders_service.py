#!/usr/bin/env python3
"""Reminders: delivers the reminders people set with 'herinner' (card: Plugins -> Reminders).

Every 20 seconds it looks in the table community_reminders for reminders that are due, and sends each one as a
direct message to the public key that set it. A failed send (radio busy, contact not reachable) is tried again
every 5 minutes, at most 6 times; after that it is dropped with a line in the log. Delivered and dropped reminders
are removed after 30 days. Nothing else is ever sent.
"""
import asyncio
import time
from typing import Any, Optional

from ..mesh_community import ensure_tables
from .base_service import BaseServicePlugin

CHECK_EVERY_S = 20
RETRY_S = 300
MAX_TRIES = 6
KEEP_DONE_S = 30 * 86400


class RemindersService(BaseServicePlugin):
    config_section = "Reminders"
    name = "reminders"
    description = "Delivers the reminders set with the herinner command, as a direct message at the chosen time"

    settings_schema = [
        {"key": "language", "label": "Language of the reminder message", "type": "enum", "default": "nl",
         "options": [
             {"value": "nl", "label": "Nederlands"}, {"value": "en", "label": "English"},
             {"value": "de", "label": "Deutsch"}, {"value": "fr", "label": "Français"},
         ],
         "help": "The reminder is sent on its own later, so there is no message to detect the language from."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        language = (cfg.get(self.config_section, "language", fallback="nl") if cfg.has_section(self.config_section) else "nl") or "nl"
        get_translator = getattr(bot, "get_translator", None)
        self.translate = get_translator(language.strip().lower()).translate if get_translator else bot.translator.translate
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        ensure_tables(self.bot.db_manager)
        self._running = True
        self._task = asyncio.get_running_loop().create_task(self._loop())
        self.logger.info("Reminders: gestart")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.deliver_due()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning(f"Reminders: fout bij controleren: {e}")
            await asyncio.sleep(CHECK_EVERY_S)

    async def deliver_due(self, now_ts: float = None) -> int:
        """Send what is due; returns how many were delivered."""
        now_ts = time.time() if now_ts is None else now_ts
        if not getattr(self.bot, "connected", True):
            return 0
        with self.bot.db_manager.connection() as conn:
            due = conn.execute("SELECT id, pubkey, name, text, tries FROM community_reminders WHERE done=0 AND due_at<=? AND next_try<=? ORDER BY due_at LIMIT 5",
                               (int(now_ts), int(now_ts))).fetchall()
            conn.execute("DELETE FROM community_reminders WHERE done!=0 AND due_at < ?", (int(now_ts - KEEP_DONE_S),))
            conn.commit()
        delivered = 0
        for rid, pubkey, name, text, tries in due:
            ok = False
            try:
                ok = await self.bot.command_manager.send_dm(pubkey, self.translate("commands.herinner.delivery", text=text),
                                                            skip_user_rate_limit=True)
            except Exception as e:  # noqa: BLE001
                self.logger.warning(f"Reminders: versturen naar {name or pubkey[:8]} mislukt: {e}")
            with self.bot.db_manager.connection() as conn:
                if ok:
                    conn.execute("UPDATE community_reminders SET done=1 WHERE id=?", (rid,))
                    delivered += 1
                elif tries + 1 >= MAX_TRIES:
                    conn.execute("UPDATE community_reminders SET done=2, tries=? WHERE id=?", (tries + 1, rid))
                    self.logger.warning(f"Reminders: herinnering #{rid} voor {name or pubkey[:8]} na {MAX_TRIES} pogingen opgegeven")
                else:
                    conn.execute("UPDATE community_reminders SET tries=?, next_try=? WHERE id=?", (tries + 1, int(now_ts + RETRY_S), rid))
                conn.commit()
        return delivered
