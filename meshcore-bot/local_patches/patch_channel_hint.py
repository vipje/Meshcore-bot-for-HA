#!/usr/bin/env python3
"""Source patch: tell people where a command works (see modules/channel_hint.py).

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

Upstream silently ignores a command that is used in a channel where it is not allowed. Two
hooks are added so that, for *every* command, the bot can answer with a short hint instead:

1. message_handler.process_message(): messages in a configured hint channel never reach the
   command pipeline (no command runs there); if the message is a command attempt (see channel_hint.py) the bot
   hints where commands do work. Runs after the greeter block, so greeting still works there.
2. settings_schema._assemble_entry(): every command card of the dashboard's Plugins page gets a
   "Hint in the public channel" setting (`[Xxx_Command] hint = off|word|args`).
3. command_manager.execute_commands(): a command with its own channel list that is used in a
   channel outside that list answers with where it does work.
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
    "modules/message_handler.py",
    """        # Now check if we should process this message for bot responses
        if not self.should_process_message(message):
            return
""",
    """        # Hint channels (e.g. a busy public channel): no commands run here, but a command attempt
        # gets a short pointer to the channels where commands do work.
        if not message.is_dm:
            from modules.channel_hint import get_channel_hint
            _hint = get_channel_hint(self.bot)
            _hint.note_message(message)   # remember that another bot spoke here
            if _hint.ignore_bot_commands and _hint.is_other_bot(message):
                return   # never answer another bot: two bots that answer each other only make noise
            if _hint.is_hint_channel(message):
                if _hint.matches_command(message):
                    await _hint.send_hint(message, yield_to_bots=True)
                return

        # Now check if we should process this message for bot responses
        if not self.should_process_message(message):
            return
""",
)

patch(
    "modules/command_manager.py",
    """            if not command.is_channel_allowed(message):
                continue

            if command.should_execute(message):""",
    """            if not command.is_channel_allowed(message):
                if not message.is_dm:
                    try:
                        from modules.channel_hint import get_channel_hint
                        _hint = get_channel_hint(self.bot)
                        # Only for commands whose own "hint" setting is on, and only when the bot itself
                        # would have recognised the message as this command.
                        if _hint.command_hint_mode(command) != "off" and command.matches_keyword(message):
                            _allowed = command.allowed_channels
                            if _allowed is None:
                                _allowed = sorted(self.monitor_channels)
                            await _hint.send_hint(message, where=list(_allowed))
                    except Exception as _e:
                        self.logger.debug("Channel hint failed: %s", _e)
                continue

            if command.should_execute(message):""",
)


patch(
    "modules/settings_schema.py",
    """    # Keys handled elsewhere shouldn't appear in the raw "Other config values"
    # editor: the enable toggle, its legacy *_enabled aliases in this section,
    # the channels field above, and aliases (managed via keywords).
    skip_keys = {"enabled", "channels", "aliases"}""",
    """    # Per-command switch for the channel hints (see modules/channel_hint.py).
    if kind == "command" and not any(f["key"].lower() == "hint" for f in fields):
        hint_field = {
            "key": "hint", "label": "Hint in the public channel", "type": "enum",
            "default": "word" if name in ("ping", "test", "help") else "off",
            "options": [
                {"value": "off", "label": "Off"},
                {"value": "word", "label": "When the command word is typed alone"},
                {"value": "args", "label": "Alone or with arguments"},
            ],
            "help": ("In a channel where the bot listens but runs no commands (see the add-on option "
                     "Public channel), answer this command word with a pointer to the channels where "
                     "commands do work."),
        }
        hint_field["value"] = _read_typed(config, section, hint_field)
        fields.append(hint_field)

    # Keys handled elsewhere shouldn't appear in the raw "Other config values"
    # editor: the enable toggle, its legacy *_enabled aliases in this section,
    # the channels and hint fields above, and aliases (managed via keywords).
    skip_keys = {"enabled", "channels", "aliases", "hint"}""",
)
