#!/usr/bin/env python3
"""AutoLanguage: reply in the language the sender typed, for every command (card: Plugins -> AutoLanguage).

Upstream already detects the language of an incoming message (modules/lang_detector.py, keyword map plus
optional langdetect) and can build a reply with a temporarily swapped translator
(BaseCommand.respond_in_sender_language). Only the built-in ``hello`` command used that on its own; this service
does nothing itself, it only carries the on/off switch. patch_sender_language_detection.py reads this section's
``enabled`` key and, when true, wraps every command dispatch in command_manager.py with that same context manager,
so it applies to all upstream commands at once. Detection only ever returns a language upstream ships translations
for (translations/*.json), so it does nothing for languages with no catalog.

Off by default: no extra airtime (only the text of a reply changes), but a bot that suddenly answers in whatever
language someone typed in is a behaviour change some operators may not want.
"""
from typing import Any

from .base_service import BaseServicePlugin


class AutoLanguageService(BaseServicePlugin):
    config_section = "AutoLanguage"
    name = "autolanguage"
    description = "Reply in the language the sender typed (all commands), instead of always the one fixed Bot > Language"

    settings_schema: list[dict[str, Any]] = []

    def __init__(self, bot: Any):
        super().__init__(bot)

    async def start(self) -> None:
        self.logger.info("AutoLanguage: gestart (antwoordt per bericht in de gedetecteerde taal van de afzender)")
        self._running = True

    async def stop(self) -> None:
        self._running = False
