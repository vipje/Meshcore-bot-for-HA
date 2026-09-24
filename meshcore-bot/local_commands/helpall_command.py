#!/usr/bin/env python3
"""
'helpall' command for the MeshCore Bot.
The full command list a regular channel user can actually use, browsed one
page at a time. Plain 'helpall' auto-advances per sender: page 1 the first
time, then page 2 the next time the same sender sends plain 'helpall' within
_PROGRESS_TTL_SECONDS, then page 3, and so on, wrapping back to page 1 after
the last page or once that window lapses. 'helpall <N>' still jumps straight
to a specific page, overriding the auto-advance for that call (but not
resetting it - the next plain 'helpall' continues from wherever the
per-sender progress already was).

Same page-at-a-time idea as the built-in 'help N' (patch_command_manager.py),
which already proved reliable specifically because it's always exactly one
message per request, paced by the person asking rather than the bot firing
several in a row. Earlier versions of this file tried to auto-send every
page in one run (chunked over the channel, then DM with a channel fallback);
both still dropped some pages in live testing, because auto-sending N
messages back-to-back is inherently less reliable than one at a time no
matter the delivery method - so this drops that idea rather than continuing
to chase it. The per-sender progress tracking replaces the "volgende:
helpall N" hint an earlier version put on every page - no longer needed
once plain 'helpall' just knows which page comes next by itself.

A separate keyword rather than extending 'help all': the literal 'help '
keyword is intercepted by CommandManager before the normal plugin loop even
runs (see check_keyword_matches in modules/command_manager.py), so a new
plugin with keyword 'help' would never be reached.

The one thing this still adds over plain 'help N': excludes admin-only and
DM-only commands, which 'help N' doesn't - not much point listing a command
from a channel context it can't run in anyway. This exclusion is shared with
'help'/'help N'/'help <command>' via local_shared/help_filter.py (see
local_patches/patch_help_filter.py), rather than a second copy of the same
checks here.
"""

import time
from typing import Any

from ..help_filter import display_name, is_public_command
from ..models import MeshMessage
from .base_command import BaseCommand

_PROGRESS_TTL_SECONDS = 5 * 60


class HelpAllCommand(BaseCommand):
    """Shows the full public command list, one page at a time, auto-advancing per sender."""

    name = "helpall"
    keywords = ["helpall"]
    description = "Volledige commandolijst, één pagina per keer (usage: helpall [paginanummer])"
    category = "basic"

    short_description = "Volledige commandolijst (pagina per pagina, onthoudt waar je was)"
    usage = "helpall [paginanummer]"
    examples = ["helpall", "helpall 2"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.helpall_enabled = self.get_config_value(
            "Helpall_Command", "enabled", fallback=True, value_type="bool"
        )
        # sender key -> (last page shown, timestamp). In-memory only: losing
        # this on a bot restart just means the next plain 'helpall' starts
        # back at page 1, which is a fine default anyway.
        self._progress: dict[str, tuple[int, float]] = {}

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.helpall_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Volledige lijst kanaal-commando's (geen admin/DM-only): 'helpall' voor pagina 1, dan 'helpall 2', 'helpall 3', ..."

    def _public_command_names(self, message: MeshMessage) -> list[str]:
        command_manager = self.bot.command_manager
        help_cmd = command_manager.commands.get("help")

        names = {
            display_name(name, cmd)
            for name, cmd in command_manager.commands.items()
            if is_public_command(name, cmd, help_cmd, message)
        }
        return sorted(names)

    def _paginate(self, names: list[str], budget: int) -> list[str]:
        pages: list[str] = []
        current: list[str] = []
        current_len = 0
        for name in names:
            added_len = len(name) + (2 if current else 0)
            if current and current_len + added_len > budget:
                pages.append(", ".join(current))
                current = [name]
                current_len = len(name)
            else:
                current.append(name)
                current_len += added_len
        if current:
            pages.append(", ".join(current))
        return pages or [""]

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip().lower()
            if content.startswith("helpall"):
                content = content[len("helpall"):].strip()

            names = self._public_command_names(message)
            max_total = self.get_max_message_length(message)
            budget = max(20, max_total - 12)  # reserve for the "Help N/M: " prefix
            pages = self._paginate(names, budget)
            total = len(pages)

            sender_key = message.sender_pubkey or message.sender_id or ""
            now = time.time()

            if content.isdigit():
                # Explicit page number: jump there, but don't touch this
                # sender's auto-advance progress - the next plain 'helpall'
                # still continues from wherever it already was.
                page_num = int(content)
            else:
                prev = self._progress.get(sender_key)
                if prev is not None and (now - prev[1]) < _PROGRESS_TTL_SECONDS:
                    page_num = prev[0] + 1 if prev[0] < total else 1
                else:
                    page_num = 1

            if not (1 <= page_num <= total):
                return await self.send_response(
                    message, self.translate("commands.helpall.bad_page", page=page_num, total=total)
                )

            if not content.isdigit():
                self._progress[sender_key] = (page_num, now)

            return await self.send_response(
                message, self.translate("commands.helpall.page", page=page_num, total=total, names=pages[page_num - 1])
            )
        except Exception as e:
            self.logger.error(f"Error executing helpall command: {e}")
            return await self.send_response(message, self.translate("commands.helpall.error", error=str(e)))
