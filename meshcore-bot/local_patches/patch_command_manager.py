#!/usr/bin/env python3
"""Source patch applied to the vendored meshcore-bot command manager.

Runs once during the Docker build, right after `git clone` (see
patch_webviewer.py for the shared rationale/mechanics).

Neither 'help' (no args) nor 'cmd' can ever list every command: both build a
single LoRa-sized message and truncate with "(N more)" once the budget runs
out, which happens well before reaching alphabetically-later commands now
that there are 40+ plugins. Adds numeric paging: 'help 1', 'help 2', ...
walk through the full command list a page at a time, so every command
(including local additions like topu/topc) is reachable, just not all in
one message.
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
    """        # Special handling for common help requests
        if command_name.lower() in ['commands', 'list', 'all']:
            # User is asking for a list of commands, show general help
            return self.get_general_help(message)

        requested_name = command_name.strip()""",
    """        # Special handling for common help requests
        if command_name.lower() in ['commands', 'list', 'all']:
            # User is asking for a list of commands, show general help
            return self.get_general_help(message)

        # Numeric argument ('help 1', 'help 2', ...): paginated full command
        # list. The compact general-help/cmd output truncates well before
        # reaching alphabetically-later commands once there are 40+ plugins,
        # so this is the only way to browse everything from the mesh itself.
        stripped = command_name.strip()
        if stripped.isdigit():
            pages = self._get_paginated_commands(message)
            page_num = int(stripped)
            total = len(pages)
            if 1 <= page_num <= total:
                return f"Help {page_num}/{total}: {pages[page_num - 1]}"
            return f"Help: pagina {page_num} bestaat niet (1-{total} beschikbaar)."

        requested_name = command_name.strip()""",
)

patch(
    "modules/command_manager.py",
    """        return f"Unknown: {command_name}. Available: {available_str}. Try 'help' for command list."

    # Prefix and suffix for general help (reserve space so suffix is never cut off)
    _HELP_PREFIX = "Bot Help: "
    _HELP_SUFFIX = " | More: 'help <command>'\"""",
    """        return f"Unknown: {command_name}. Available: {available_str}. Try 'help' for command list."

    def _get_paginated_commands(self, message: MeshMessage | None = None) -> list[str]:
        \"\"\"Split all available command names into LoRa-sized pages for 'help N'.\"\"\"
        from .help_filter import display_name, is_public_command
        help_cmd = self.commands.get('help')
        primary_names = sorted({
            display_name(name, cmd)
            for name, cmd in self.commands.items()
            if is_public_command(name, cmd, help_cmd, message)
        })

        max_total = 140
        if help_cmd and message and hasattr(help_cmd, 'get_max_message_length'):
            max_total = help_cmd.get_max_message_length(message)
        # Reserve room for the "Help N/M: " prefix this page will be sent with.
        budget = max(20, max_total - 12)

        pages: list[str] = []
        current: list[str] = []
        current_len = 0
        for name in primary_names:
            added_len = len(name) + (2 if current else 0)
            if current and current_len + added_len > budget:
                pages.append(', '.join(current))
                current = [name]
                current_len = len(name)
            else:
                current.append(name)
                current_len += added_len
        if current:
            pages.append(', '.join(current))
        return pages or ['']

    # Prefix and suffix for general help (reserve space so suffix is never cut off)
    _HELP_PREFIX = "Bot Help: "
    _HELP_SUFFIX = " | More: 'help <cmd>' or 'help 1', 'help 2'..\"""",
)
