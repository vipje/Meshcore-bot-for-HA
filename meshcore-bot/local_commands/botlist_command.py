#!/usr/bin/env python3
"""
'botlist' command for the MeshCore Bot (admin only).

Other bots on the mesh are recognised by the robot emoji or the word "bot" in their name (see
modules/channel_hint.py). This command overrules that for single names:

  botlist                 show the hand-made lists
  botlist add <name>      always treat this name as a bot
  botlist not <name>      never treat this name as a bot (a person called Talbot, say)
  botlist del <name>      remove the name from both lists (automatic recognition applies again)
  botlist check <name>    say whether a name counts as a bot, and why

Bots are not greeted by the greeter, and the bot stays quiet in the public channel when one of
them has already answered. The lists live in the bot's database and survive restarts.
"""

from typing import Any

from ..channel_hint import get_channel_hint
from ..models import MeshMessage
from .base_command import BaseCommand

ADD_WORDS = {"add", "voeg", "toevoegen", "bot"}
NOT_WORDS = {"not", "geen", "nobot", "mens"}
DEL_WORDS = {"del", "delete", "rm", "remove", "weg", "verwijder"}
CHECK_WORDS = {"check", "test", "is"}
LIST_WORDS = {"", "list", "lijst", "show"}


class BotlistCommand(BaseCommand):
    """Mark names as bot or not a bot."""

    name = "botlist"
    keywords = ["botlist", "botlijst"]
    description = "Namen als bot markeren of juist niet (admin)"
    category = "admin"

    short_description = "Bots markeren (admin)"
    usage = "botlist [add|not|del|check] [naam]"
    examples = ["botlist", "botlist add Echobot", "botlist not Talbot", "botlist del Echobot", "botlist check DX1ABC-BOT"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.botlist_enabled = self.get_config_value(
            "Botlist_Command", "enabled", fallback=True, value_type="bool"
        )

    def requires_admin_access(self) -> bool:
        return True

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.botlist_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return (
            "botlist toont de lijsten; botlist add <naam> = altijd bot, botlist not <naam> = nooit bot, "
            "botlist del <naam> = weg uit de lijsten, botlist check <naam> (admin)."
        )

    def _arguments(self, message: MeshMessage) -> list:
        """Words after the command word (any '!' in front is ignored)."""
        tokens = (message.content or "").split()
        for i, token in enumerate(tokens):
            if token.lstrip("!/").lower() in self.keywords:
                return tokens[i + 1:]
        return []

    async def execute(self, message: MeshMessage) -> bool:
        try:
            hint = get_channel_hint(self.bot)
            args = self._arguments(message)
            sub = args[0].lower() if args else ""
            name = " ".join(args[1:]).strip()

            if sub in LIST_WORDS:
                marked, never = hint.manual_lists()
                if not marked and not never:
                    text = self.translate("commands.botlist.none")
                else:
                    parts = []
                    if marked:
                        parts.append(self.translate("commands.botlist.bots_list", names=", ".join(marked)))
                    if never:
                        parts.append(self.translate("commands.botlist.never_list", names=", ".join(never)))
                    text = self.translate("commands.botlist.header") + " " + " | ".join(parts)
                return await self.send_response(message, text)

            if sub in ADD_WORDS | NOT_WORDS | DEL_WORDS | CHECK_WORDS and not name:
                return await self.send_response(message, self.translate("commands.botlist.missing_name", sub=sub))

            if sub in CHECK_WORDS:
                is_bot, reason = hint.classify(name)
                verdict = self.translate("commands.botlist.is_bot") if is_bot else self.translate("commands.botlist.not_bot")
                return await self.send_response(
                    message, self.translate("commands.botlist.check_result", name=name, verdict=verdict, reason=reason)
                )

            if sub in ADD_WORDS:
                was = hint.set_manual(name, True)
                note = "" if was is not False else self.translate("commands.botlist.moved_from_never")
                return await self.send_response(message, self.translate("commands.botlist.added", name=name, note=note))

            if sub in NOT_WORDS:
                was = hint.set_manual(name, False)
                note = "" if was is not True else self.translate("commands.botlist.moved_from_bots")
                return await self.send_response(message, self.translate("commands.botlist.excluded", name=name, note=note))

            if sub in DEL_WORDS:
                was = hint.set_manual(name, None)
                if was is None:
                    return await self.send_response(message, self.translate("commands.botlist.not_listed", name=name))
                after, _ = hint.classify(name)
                verdict = self.translate("commands.botlist.is_bot") if after else self.translate("commands.botlist.not_bot")
                return await self.send_response(
                    message,
                    self.translate("commands.botlist.deleted", name=name, verdict=verdict),
                )

            return await self.send_response(
                message, self.translate("commands.botlist.usage")
            )
        except ValueError as e:
            return await self.send_response(message, self.translate("commands.botlist.value_error", error=str(e)))
        except Exception as e:
            self.logger.error(f"Error executing botlist command: {e}")
            return await self.send_response(message, self.translate("commands.botlist.error", error=str(e)))
