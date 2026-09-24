#!/usr/bin/env python3
"""Source patch: the greeter does not greet other bots (see modules/channel_hint.py).

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

Upstream's greeter welcomes every first-time sender in its channels. Another bot ("DX1ABC-BOT",
"Name|🤖", or a name an admin marked with `botlist add`) gets "welcome, want to test the bot?"
for nothing, and two bots that answer each other only make noise. `ChannelHint.is_other_bot()`
(robot emoji, the word bot, and the hand-made lists of the `botlist` command) decides.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")


patch(
    "modules/commands/greeter_command.py",
    """        # Must have a channel name
        if not message.channel:
            return False

        # Check channel access using standardized method (with case-insensitive fallback)""",
    """        # Must have a channel name
        if not message.channel:
            return False

        # Never greet another bot (robot emoji, the word bot, or marked with `botlist add`)
        try:
            from modules.channel_hint import get_channel_hint
            if get_channel_hint(self.bot).is_other_bot(message):
                self.logger.debug(f"Greeter: {message.sender_id} is a bot, not greeting")
                return False
        except Exception as e:  # never let this break the greeter
            self.logger.debug(f"Greeter bot check failed: {e}")

        # Check channel access using standardized method (with case-insensitive fallback)""",
)
