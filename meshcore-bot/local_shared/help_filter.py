"""Shared "is this a public, channel-usable command" filter.

Used by the vendored help_command.py and command_manager.py (both patched -
see local_patches/patch_help_filter.py) and by the local helpall_command.py,
so every command-listing surface ('help', 'help N' paging, 'help <command>',
'helpall') applies the same exclusion instead of three+ separate copies of
the same checks silently drifting apart over time.

Excludes:
- Admin-only commands (checked via each command's own requires_admin_access(),
  which reads the [Admin_ACL] admin_commands allow-list).
- Hardcoded DM-only commands (not detectable via requires_admin_access() -
  these gate on message.is_dm in their own can_execute()).
- A small manually-curated set of other commands not meant for a regular
  channel user to browse to (e.g. greeter, an automatic welcome-message
  feature rather than something anyone would type themselves).
- Disabled commands (self.<name>_enabled == False) - a disabled command
  (e.g. worldcup/airplanes, both off by default here) still loads and
  appears in the command registry, it just never responds.
- Commands not valid for the asking channel (existing per-command channel
  overrides / channel_keywords), when a help_cmd + message are given.
"""

from typing import Any, Optional

DM_ONLY = {
    "schedule",       # dm_only config, defaults to True
    "announcements",  # can_execute always requires message.is_dm
}
ALWAYS_HIDDEN = {
    "greeter",  # automatic welcome-message feature, not a user-typed command
}


def is_public_command(name: str, cmd: Any, help_cmd: Any = None, message: Optional[Any] = None) -> bool:
    primary = getattr(cmd, "name", name)
    if primary in DM_ONLY or primary in ALWAYS_HIDDEN:
        return False
    if hasattr(cmd, "requires_admin_access") and cmd.requires_admin_access():
        return False
    if any(v is False for k, v in vars(cmd).items() if k.endswith("_enabled")):
        return False
    if help_cmd is not None and message is not None and hasattr(help_cmd, "_is_command_valid_for_channel"):
        if not help_cmd._is_command_valid_for_channel(name, cmd, message):
            return False
    return True


def display_name(name: str, cmd: Any) -> str:
    """The short word actually typed to trigger a command, for help displays.

    A command's `.name` is its internal/canonical identifier, not
    necessarily something you can type - e.g. topusers_command.py has
    name="topusers" but keywords=["topu"], so only "topu" ever triggers it.
    Showing `.name` in help (the previous behaviour, inherited from
    upstream's own use of `.name` everywhere) is actively misleading for any
    command where these differ. `keywords[0]` is each command's own primary
    trigger, so use that when present.
    """
    keywords = getattr(cmd, "keywords", None)
    if keywords:
        return keywords[0]
    return getattr(cmd, "name", name)
