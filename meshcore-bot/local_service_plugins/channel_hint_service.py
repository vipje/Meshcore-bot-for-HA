#!/usr/bin/env python3
"""Settings card for the channel hint ([ChannelHint]), on the dashboard's Plugins page.

The hint itself is not a plugin: it is one shared object hooked into the message handler (see
modules/channel_hint.py and patch_channel_hint.py). This service only exists so the hint gets a card with typed
fields, like every other plugin, instead of add-on options. It does nothing at run time.

Changes saved on the card apply within about 30 seconds without a restart: the hint re-reads its section of
the bot's config, which the bot reloads after every save on the Plugins page.
"""

from typing import Any

from .base_service import BaseServicePlugin


class ChannelHintService(BaseServicePlugin):
    """Card only; the work is done by modules/channel_hint.py."""

    config_section = "ChannelHint"
    name = "channelhint"
    description = "Pointer to the channels where commands work, for a channel where the bot listens but runs no commands"

    settings_schema = [
        {"key": "channels", "label": "Channels that get a hint (no commands there)", "type": "list", "default": [],
         "help": ("Channels where the bot listens but runs no commands, for example the public channel. Someone who types a "
                  "command word there gets a pointer to the channels below. Comma-separated, name exactly as on your radio.")},
        {"key": "where", "label": "Channels where commands do work", "type": "list", "default": [],
         "help": "Shown in the hint, for example #bot, #test. Comma-separated."},
        {"key": "message", "label": "Hint text", "type": "str",
         "default": ("We helpen je heel graag verder in {channels} || Voor commando's en tests ben je welkom in {channels} || "
                     "Hier reageer ik niet op commando's, in {channels} wel! || Tip: probeer het in {channels}, daar help ik je graag"),
         "help": ("{channels} becomes the list above. Several texts separated by || : the bot picks one at random and never the "
                  "same one twice in a row in a channel, so someone who types test three times does not get the same answer.")},
        {"key": "restricted_message", "label": "Text when a command is used in the wrong channel", "type": "str",
         "default": "Dat commando werkt hier niet. We helpen je graag verder in: {channels}",
         "help": ("Sent when someone uses a command in a channel outside that command's own channel list. Several texts "
                  "separated by || are picked at random, like the hint text.")},
        {"key": "ignore_words", "label": "Words that never get a hint", "type": "list", "default": ["hello", "hi", "hey"],
         "help": "Greetings that are also command words; answering them would only be noise."},
        {"key": "cooldown_seconds", "label": "At most one hint per channel every", "type": "int", "default": 120,
         "min": 10, "max": 3600, "unit": "s"},
        {"key": "user_cooldown_seconds", "label": "At most one hint per person every", "type": "int", "default": 600,
         "min": 10, "max": 86400, "unit": "s"},
        {"key": "yield_seconds", "label": "Wait for other bots first", "type": "int", "default": 15,
         "min": 0, "max": 120, "unit": "s",
         "help": ("Other bots in the region would answer the same message. The bot waits this long (plus a random extra of up to "
                  "8 seconds) and stays quiet if another bot answered meanwhile. 0 = do not wait. The greeter has its own wait "
                  "(dead_air_delay_seconds on its card).")},
        {"key": "ignore_bot_commands", "label": "Do not answer other bots", "type": "bool", "default": True,
         "help": ("Commands typed by another bot in a channel are ignored (bots are recognised by the two fields below and by the "
                  "dashboard's Bots page). Prevents two bots from answering each other for ever. Direct messages are never ignored.")},
        {"key": "bot_markers", "label": "Robot emoji that mark a bot", "type": "list", "default": ["🤖"],
         "help": "A name that contains one of these is a bot."},
        {"key": "bot_words", "label": "Words that mark a bot", "type": "list", "default": ["bot"],
         "help": ("A name with one of these words in it (any case, not followed by a letter: DX1ABC-BOT, Echobot) is a bot. "
                  "Single names can be set by hand on the dashboard's Bots page.")},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
