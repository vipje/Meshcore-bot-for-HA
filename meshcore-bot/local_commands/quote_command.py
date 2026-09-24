#!/usr/bin/env python3
"""
'quote' command for the MeshCore Bot.
Sends a random quote from a locally bundled list (no internet needed).
"""

import random
from typing import Any

from ..local_data.quotes import QUOTES
from ..models import MeshMessage
from .base_command import BaseCommand


class QuoteCommand(BaseCommand):
    """Sends a random quote from a locally bundled list."""

    name = "quote"
    keywords = ["quote", "citaat"]
    description = "Willekeurig citaat"
    category = "fun"

    short_description = "Willekeurig citaat"
    usage = "quote"
    examples = ["quote", "citaat"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.quote_enabled = self.get_config_value(
            "Quote_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.quote_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Stuurt een willekeurig citaat uit een lokale lijst."

    async def execute(self, message: MeshMessage) -> bool:
        try:
            text, author = random.choice(QUOTES)
            response = f'"{text}" - {author}'
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing quote command: {e}")
            return await self.send_response(message, self.translate("commands.quote.error", error=str(e)))
