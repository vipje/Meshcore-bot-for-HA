#!/usr/bin/env python3
"""
'weetje' command for the MeshCore Bot: a Dutch did-you-know from a fixed list (modules/local_data/weetjes.py).

  weetje     a random fact; the bot goes through the whole list before repeating one

The facts are in Dutch only (they are content, not interface text).
"""

import random
from typing import Any

from ..local_data.weetjes import WEETJES
from ..models import MeshMessage
from .base_command import BaseCommand


class WeetjeCommand(BaseCommand):
    """A random Dutch did-you-know."""

    name = "weetje"
    keywords = ["weetje", "wistje"]
    description = "Een willekeurig weetje (Nederlandstalig)"
    category = "fun"

    short_description = "Willekeurig weetje"
    usage = "weetje"
    examples = ["weetje"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.weetje_enabled = self.get_config_value("Weetje_Command", "enabled", fallback=True, value_type="bool")
        self._queue: list = []

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.weetje_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def next_fact(self) -> str:
        if not self._queue:
            self._queue = list(WEETJES)
            random.shuffle(self._queue)
        return self._queue.pop()

    async def execute(self, message: MeshMessage) -> bool:
        try:
            return await self.send_response(message, self.next_fact())
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing weetje command: {e}")
            return await self.send_response(message, self.translate("commands.weetje.error", error=str(e)))
