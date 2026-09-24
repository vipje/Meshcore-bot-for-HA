#!/usr/bin/env python3
"""Source patch: reply in the sender's own language, for every command (see local_service_plugins/autolanguage_service.py).

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

Upstream already has everything needed: modules/lang_detector.py detects the language of an incoming message
(keyword map for short greetings, optional langdetect for longer text), and
BaseCommand.respond_in_sender_language(message) is a context manager that, for the duration of the ``with`` block,
makes every ``self.translate(...)`` call in that task use a translator for the detected language instead of the
bot-wide default -- but only the built-in ``hello`` command used it. CommandManager.execute_command() (and the two
other places that call ``command.execute(...)``: queued commands and the admin advert command) is the one place
every command dispatch passes through, so wrapping the three call sites there turns it on everywhere at once,
without editing 76 individual command files. Gated on [AutoLanguage] enabled (off by default) so this is a
deliberate opt-in, not a silent behaviour change.
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


def _lang_ctx_line(indent: str) -> str:
    return (
        f"{indent}_lang_ctx = command.respond_in_sender_language(message) "
        f"if self.bot.config.getboolean('AutoLanguage', 'enabled', fallback=False) "
        f"else contextlib.nullcontext()\n"
    )


# 1. Queued commands (bypasses normal cooldown checks).
patch(
    "modules/command_manager.py",
    """        # Execute directly
        success = await command.execute(message)""",
    _lang_ctx_line("        ") + """        with _lang_ctx:
            success = await command.execute(message)""",
)

# 2. The admin advert command's own dispatch path.
patch(
    "modules/command_manager.py",
    """        command = self.commands['advert']
        await command.execute(message)""",
    """        command = self.commands['advert']
"""
    + _lang_ctx_line("        ")
    + """        with _lang_ctx:
            await command.execute(message)""",
)

# 3. The main dispatch path for a normal incoming command.
patch(
    "modules/command_manager.py",
    """                    # Execute the command
                    success = await command.execute(message)""",
    _lang_ctx_line("                    ") + """                    with _lang_ctx:
                        success = await command.execute(message)""",
)
