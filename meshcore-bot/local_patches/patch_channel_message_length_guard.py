#!/usr/bin/env python3
"""Adds an auto-split length guard to send_channel_message, mirroring the one
send_dm already has.

Runs once during the Docker build, right after `git clone` (see
patch_webviewer.py for the shared rationale/mechanics).

send_dm has a "Central DM length guard" that auto-splits oversized content
into chunks via split_text_into_utf8_chunks(). send_channel_message had no
equivalent: content longer than the radio's actual packet budget was handed
straight to meshcore.commands.send_chan_msg() with no check, and got cut off
somewhere below that call (in the meshcore library or firmware) with no
indication - silently, mid-word, no ellipsis. A long 'stem <question>' poll
was the first place this showed up, but the fix belongs here rather than in
poll_command.py (or any other single command) since every command's channel
replies go through this one function - fixing it here covers all of them at
once, including any added later, without each one needing its own length
check.
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
    "modules/command_manager.py",
    """        if not self.bot.connected or not self.bot.meshcore:
            return False

        if self.bot.is_radio_zombie:
            self.bot.logger.warning("send_channel_message suppressed — radio is in zombie state; power cycle required")
            return False
        if self.bot.is_radio_offline:
            self.bot.logger.warning(
                "send_channel_message suppressed — radio is offline (repeated send timeouts)"
            )
            return False""",
    """        if not self.bot.connected or not self.bot.meshcore:
            return False

        # Length guard, mirroring send_dm's own "Central DM length guard":
        # auto-split oversized content instead of handing it straight to
        # meshcore.commands.send_chan_msg() below, which silently truncates
        # (mid-word, no ellipsis) rather than erroring. 160 total minus the
        # "<botname>: " prefix the firmware adds, matching BaseCommand.
        # get_max_message_length()'s own channel-message formula.
        bot_name = self.bot.config.get('Bot', 'bot_name', fallback='Bot')
        channel_max_bytes = max(130, 160 - len(bot_name.encode('utf-8')) - 2)
        content_bytes = len(content.encode('utf-8'))
        if content_bytes > channel_max_bytes:
            chunks = self.split_text_into_utf8_chunks(content, channel_max_bytes)
            self.logger.warning(
                "Channel message to %s exceeds %d UTF-8 bytes (%d); auto-splitting into %d chunk(s)",
                channel, channel_max_bytes, content_bytes, len(chunks),
            )
            rate_limit_seconds = self.bot.config.getfloat('Bot', 'bot_tx_rate_limit_seconds', fallback=1.0)
            sleep_time = max(rate_limit_seconds + 0.5, 1.0)
            for i, chunk in enumerate(chunks):
                if i > 0:
                    await self.bot.bot_tx_rate_limiter.wait_for_tx()
                    await asyncio.sleep(sleep_time)
                if not await self.send_channel_message(
                    channel, chunk,
                    command_id=command_id,
                    skip_user_rate_limit=skip_user_rate_limit if i == 0 else True,
                    rate_limit_key=rate_limit_key if i == 0 else None,
                    scope=scope,
                    timestamp=timestamp,
                ):
                    self.logger.warning(
                        "Auto-split channel message failed at chunk %d of %d", i + 1, len(chunks)
                    )
                    return False
            return True

        if self.bot.is_radio_zombie:
            self.bot.logger.warning("send_channel_message suppressed — radio is in zombie state; power cycle required")
            return False
        if self.bot.is_radio_offline:
            self.bot.logger.warning(
                "send_channel_message suppressed — radio is offline (repeated send timeouts)"
            )
            return False""",
)
