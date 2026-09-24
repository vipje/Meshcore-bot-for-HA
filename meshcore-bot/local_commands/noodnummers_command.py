#!/usr/bin/env python3
"""
'noodnummers' command for the MeshCore Bot: the emergency and help numbers for this region.

  noodnummers      (or: nood) always starts with 112, then the region's own numbers

The region's numbers are filled in once on the card (Plugins -> noodnummers, field "numbers"), for example
"Huisartsenpost: 088-1234567 | Storing gemeente: 14 0495". Without them the reply has the national numbers.
The mesh is no emergency line: nothing guarantees a message arrives, so the reply always says to call 112.
Asked in a channel, the answer goes as a direct message to the one who asked (card: "Answer by direct message",
on by default); when that DM cannot be sent it comes in the channel.
"""

from typing import Any

from ..mesh_community import REPLY_BY_DM_FIELD, fit_bytes, reply_private
from ..models import MeshMessage
from .base_command import BaseCommand


class NoodnummersCommand(BaseCommand):
    """Emergency and help numbers (112 first, then the region's own numbers from the card)."""

    name = "noodnummers"
    keywords = ["noodnummers", "nood"]
    description = "Noodnummers en hulpnummers voor deze regio (112 eerst)"
    category = "emergency"

    short_description = "Noodnummers en hulpnummers voor de regio"
    usage = "noodnummers"
    examples = ["noodnummers"]

    settings_schema = [
        {"key": "numbers", "label": "Numbers for this region", "type": "str", "default": "",
         "help": ("Shown after 112, separated with |, for example: Huisartsenpost: 088-1234567 | Storing gemeente: 14 0495. "
                  "Empty: the national numbers (police without urgency, animal ambulance).")},
        REPLY_BY_DM_FIELD,
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.nood_enabled = self.get_config_value("Noodnummers_Command", "enabled", fallback=True, value_type="bool")
        self.numbers = (self.get_config_value("Noodnummers_Command", "numbers", fallback="") or "").strip()
        self.reply_by_dm = self.get_config_value("Noodnummers_Command", "reply_by_dm", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.nood_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.noodnummers.help")

    def build(self, max_bytes: int) -> str:
        numbers = self.numbers or self.translate("commands.noodnummers.national")
        return fit_bytes(self.translate("commands.noodnummers.reply", numbers=numbers), max_bytes)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            return await reply_private(self, message, self.build(self.get_max_message_length(message)))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing noodnummers command: {e}")
            return await self.send_response(message, self.translate("commands.noodnummers.error", error=str(e)))
