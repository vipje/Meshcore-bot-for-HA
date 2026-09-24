#!/usr/bin/env python3
"""Source patch applied to the vendored meshcore-bot command manager.

Runs once during the Docker build, right after `patch_command_manager.py`
(see patch_webviewer.py for the shared rationale/mechanics).

Sixth patch: when a user triggers a command that is administratively
disabled (e.g. [Airplanes_Command] enabled = false), execute_commands()'s
can_execute_now() check fails and the bot stays completely silent - no
different from a command that simply isn't loaded. It already has an
elif-chain right there that DOES speak up for other can_execute_now()
failures (DM-only, admin-only, cooldown), so this just adds one more
branch to that chain for the "disabled" case. Every toggleable plugin
exposes its own flag as `self.<name>_enabled` (confirmed across
help/cmd/wx/aqi/airplanes/joke/stats/sports/alert/satpass/webviewer), so
this is read generically via getattr instead of hardcoding a list of
commands.
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
    """                if not command.can_execute_now(message):
                    response_sent = False
                    # For DM-only commands in public channels, only show error if channel is allowed
                    # (i.e., channel is in monitor_channels or command's allowed_channels)
                    # This prevents prompting users in channels where the command shouldn't work at all
                    if command.requires_dm and not message.is_dm:""",
    """                if not command.can_execute_now(message):
                    response_sent = False
                    # Command explicitly turned off via its own '[Xxx_Command] enabled = false'
                    # config toggle. Checked first so a disabled command reports itself as
                    # disabled rather than falling through to the DM/admin/cooldown branches
                    # below (which don't apply and would otherwise stay silent instead).
                    command_enabled_flag = getattr(command, f"{command.name}_enabled", True)
                    if command_enabled_flag is False:
                        await self.send_response(
                            message,
                            f"Sorry, '{command_name}' staat momenteel uit - er wordt aan gewerkt!",
                        )
                        response_sent = True
                    # For DM-only commands in public channels, only show error if channel is allowed
                    # (i.e., channel is in monitor_channels or command's allowed_channels)
                    # This prevents prompting users in channels where the command shouldn't work at all
                    elif command.requires_dm and not message.is_dm:""",
)
