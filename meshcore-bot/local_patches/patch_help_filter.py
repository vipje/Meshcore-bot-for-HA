#!/usr/bin/env python3
"""Applies the shared public-command filter (local_shared/help_filter.py) to
every command-listing surface in the vendored help_command.py.

Runs once during the Docker build, right after `git clone` (see
patch_webviewer.py for the shared rationale/mechanics). Companion to the
_get_paginated_commands patch in patch_command_manager.py ('help N') and
local_commands/helpall_command.py - together these make 'help', 'help N',
'help <command>' and 'helpall' all agree on what counts as a public,
channel-usable command (no admin-only, DM-only, or disabled commands).

Also changes what bare 'help' shows: instead of the busiest commands by
usage stats, a random sample of public commands each time, plus a pointer to
'helpall' for the full list - 'help' is meant as a taste/discovery prompt,
not a second copy of the full reference 'helpall' already covers on its own
terms (paged, no length-truncated "(N more)").
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


FILE = "modules/commands/help_command.py"

# 1. 'help <command>': don't reveal an admin-only/DM-only/disabled command's
#    help text - treat it the same as an unknown command name.
patch(
    FILE,
    """        if command:
            # Pass message context to get_help_text if the method supports it""",
    """        from ..help_filter import is_public_command
        if command and not is_public_command(normalized_name, command, self, message):
            command = None
        if command:
            # Pass message context to get_help_text if the method supports it""",
)

# 2. Bare 'help': the primary_names set that both the popularity-sorted list
#    and the command_counts backfill loop are constrained to (see
#    get_available_commands_list further down) - fixing it here also fixes
#    the popularity path without a second patch there.
patch(
    FILE,
    """            # Build a set of all primary command names and ensure they map to themselves
            # Filter by channel when message is provided
            primary_names = set()
            for cmd_name, cmd_instance in self.bot.command_manager.commands.items():
                if not self._is_command_valid_for_channel(cmd_name, cmd_instance, message):
                    continue
                primary_name = cmd_instance.name if hasattr(cmd_instance, 'name') else cmd_name
                primary_names.add(primary_name)
                # Ensure primary name maps to itself in keyword_mappings
                keyword_mappings[primary_name.lower()] = primary_name""",
    """            # Build a set of all primary command names and ensure they map to themselves
            # Filter by channel when message is provided
            from ..help_filter import display_name, is_public_command
            primary_names = set()
            for cmd_name, cmd_instance in self.bot.command_manager.commands.items():
                if not is_public_command(cmd_name, cmd_instance, self, message):
                    continue
                primary_name = display_name(cmd_name, cmd_instance)
                primary_names.add(primary_name)
                # Ensure primary name maps to itself in keyword_mappings
                keyword_mappings[primary_name.lower()] = primary_name""",
)

# 3. Bare 'help', no-usage-stats-yet fallback (fresh command_counts, before
#    any command_stats rows exist).
patch(
    FILE,
    """            else:
                # Fallback: use all primary command names (filtered by channel)
                command_names = sorted([
                    cmd.name if hasattr(cmd, 'name') else name
                    for name, cmd in self.bot.command_manager.commands.items()
                    if self._is_command_valid_for_channel(name, cmd, message)
                ])""",
    """            else:
                # Fallback: use all primary command names (filtered by channel)
                from ..help_filter import display_name, is_public_command
                command_names = sorted([
                    display_name(name, cmd)
                    for name, cmd in self.bot.command_manager.commands.items()
                    if is_public_command(name, cmd, self, message)
                ])""",
)

# 4. Bare 'help', exception fallback.
patch(
    FILE,
    """            self.logger.error(f"Error getting available commands list: {e}")
            # Fallback to simple list of all command names (filtered by channel)
            command_names = sorted([
                cmd.name if hasattr(cmd, 'name') else name
                for name, cmd in self.bot.command_manager.commands.items()
                if self._is_command_valid_for_channel(name, cmd, message)
            ])""",
    """            self.logger.error(f"Error getting available commands list: {e}")
            # Fallback to simple list of all command names (filtered by channel)
            from ..help_filter import display_name, is_public_command
            command_names = sorted([
                display_name(name, cmd)
                for name, cmd in self.bot.command_manager.commands.items()
                if is_public_command(name, cmd, self, message)
            ])""",
)

# 5. Bare 'help': a link to the full command list when [Help_Command] list_url is set (card field, see step 6),
#    otherwise a random sample of public commands instead of the busiest
#    ones, pointing to 'helpall' for the full list. Replaces the whole method
#    body (which otherwise supports a [Keywords] help = ... config override
#    and a couple of legacy fallback shapes) rather than patching around the
#    edges, since none of that matters once the answer is always "sample the
#    filtered public list".
patch(
    "modules/command_manager.py",
    """    def get_general_help(self, message: MeshMessage | None = None) -> str:
        \"\"\"Get general help text from config (LoRa-friendly compact format).

        When message is provided, only lists commands valid for the message's channel.
        Reserves space for the suffix so the message always ends with | More: 'help <command>'.
        \"\"\"
        # Prefer keywords config if user has customized help
        if 'help' in self.keywords:
            return self.keywords['help']
        # Fallback: build compact list from available commands (filtered by channel)
        if 'help' in self.commands:
            help_command = self.commands['help']
            if hasattr(help_command, 'get_available_commands_list'):
                max_list = None
                if message and hasattr(help_command, 'get_max_message_length'):
                    max_total = help_command.get_max_message_length(message)
                    max_list = max_total - len(self._HELP_PREFIX) - len(self._HELP_SUFFIX)
                available_str = help_command.get_available_commands_list(message, max_length=max_list)
                return f"{self._HELP_PREFIX}{available_str}{self._HELP_SUFFIX}"
        # Last resort: simple list of command names (filtered by channel when message provided)
        help_cmd = self.commands.get('help')
        if help_cmd and hasattr(help_cmd, '_is_command_valid_for_channel') and message:
            primary_names = sorted([
                cmd.name if hasattr(cmd, 'name') else name
                for name, cmd in self.commands.items()
                if help_cmd._is_command_valid_for_channel(name, cmd, message)
            ])
        else:
            primary_names = sorted([
                cmd.name if hasattr(cmd, 'name') else name
                for name, cmd in self.commands.items()
            ])
        # Truncate list to reserve space for suffix when message (and thus max length) is known
        if message and help_cmd and hasattr(help_cmd, 'get_max_message_length'):
            max_total = help_cmd.get_max_message_length(message)
            max_list = max_total - len(self._HELP_PREFIX) - len(self._HELP_SUFFIX)
            if hasattr(help_cmd, '_format_commands_list_to_length'):
                list_str = help_cmd._format_commands_list_to_length(primary_names, max_list)
            else:
                list_str = ', '.join(primary_names)
        else:
            list_str = ', '.join(primary_names)
        return f"{self._HELP_PREFIX}{list_str}{self._HELP_SUFFIX}\"""",
    """    def get_general_help(self, message: MeshMessage | None = None) -> str:
        \"\"\"Get general help text: a random sample of public commands, pointing to 'helpall' for the full list.\"\"\"
        import random
        from .help_filter import display_name, is_public_command
        help_cmd = self.commands.get('help')
        # With a link to the full command list set on the help card, bare 'help' sends that link instead of a sample.
        list_url = (self.bot.config.get('Help_Command', 'list_url', fallback='') or '').strip()
        if list_url:
            if help_cmd is not None and hasattr(help_cmd, 'translate'):
                return help_cmd.translate('commands.help.list_link', url=list_url)
            return f"Alle commando's met uitleg: {list_url} | help <commando> = uitleg hier"
        primary_names = sorted({
            display_name(name, cmd)
            for name, cmd in self.commands.items()
            if is_public_command(name, cmd, help_cmd, message)
        })
        prefix = "Help: "
        sample_suffix = " | help <cmd>=uitleg, helpall=alles"
        sample_size = min(8, len(primary_names))
        sample = sorted(random.sample(primary_names, sample_size)) if primary_names else []
        max_total = 140
        if message and help_cmd and hasattr(help_cmd, 'get_max_message_length'):
            max_total = help_cmd.get_max_message_length(message)
        max_list = max(20, max_total - len(prefix) - len(sample_suffix))
        if help_cmd and hasattr(help_cmd, '_format_commands_list_to_length'):
            list_str = help_cmd._format_commands_list_to_length(sample, max_list)
        else:
            list_str = ', '.join(sample)
        return f"{prefix}{list_str}{sample_suffix}\"""",
)


# 6. The help card gets a field for that link (Plugins -> help: "Link to the full command list").
patch(
    "modules/commands/help_command.py",
    """    usage = "help [command]"
    examples = ["help", "help wx"]
""",
    """    usage = "help [command]"
    examples = ["help", "help wx"]

    settings_schema = [
        {"key": "list_url", "label": "Link to the full command list", "type": "str", "default": "",
         "help": ("When set, a bare 'help' answers with this link (for example a page with every command and what it does) "
                  "instead of a few random commands. 'help <command>' and 'help 2' stay as they are. Keep it short: it "
                  "has to fit one mesh message.")},
    ]
""",
)
