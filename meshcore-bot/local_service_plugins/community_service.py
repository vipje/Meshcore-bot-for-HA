#!/usr/bin/env python3
"""Community: keeps the archive behind DX Jacht ('dx') and Mesh RPG ('xp', 'badge') up to date (card: Plugins -> Community).

Upstream keeps its statistics only 7 days (by default). Every 10 minutes this service copies a summary per person per
day (messages, bot commands, best hop count) into the bot's own tables (modules/mesh_archive.py), so records and XP
last. It only reads upstream's tables and writes its own; it never touches the radio. With the service off the
commands still update the archive whenever someone uses them, but days nobody asked about can then be missed.
"""
import asyncio
from typing import Any, Optional

from ..mesh_archive import ensure_archive, sync
from .base_service import BaseServicePlugin

INTERVAL_S = 600
FIRST_DELAY_S = 30


class CommunityService(BaseServicePlugin):
    config_section = "Community"
    name = "community"
    description = "Keeps the archive for DX Jacht (dx) and Mesh RPG (xp, badge) beyond the 7 days the bot's statistics last"

    def __init__(self, bot: Any):
        super().__init__(bot)
        self._task: Optional[asyncio.Task] = None
        self.last_sync = 0.0

    async def start(self) -> None:
        ensure_archive(self.bot.db_manager)
        self._running = True
        self._task = asyncio.get_running_loop().create_task(self._loop())
        self.logger.info("Community: gestart (archief voor dx, xp en badge, elke 10 min)")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(FIRST_DELAY_S)
        while self._running:
            try:
                await asyncio.to_thread(sync, self.bot, None, True)
                self.last_sync = asyncio.get_running_loop().time()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning(f"Community: archief bijwerken mislukt: {e}")
            await asyncio.sleep(INTERVAL_S)
