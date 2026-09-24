#!/usr/bin/env python3
"""Source patch: stop the contact-capacity cleanup from repeating a round that cannot remove anything.

RepeaterManager.manage_contact_list() runs on every new contact while the radio's contact list is (nearly) full.
With the firmware set to "overwrite the oldest" (autoadd 0x03, as here) the list is always full and every contact on
it was heard lately, so each round finds nothing to remove yet logs three warnings and eight info lines - about
every 50 minutes, all day. After a round that removed nothing, further rounds are skipped for
QUIET_AFTER_NOOP_SECONDS (6 hours) with one line in the log; a round that did remove something resets that, so real
cleanups are never held back.
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
    "modules/repeater_manager.py",
    """    async def manage_contact_list(self, auto_cleanup: bool = True) -> dict:
        \"\"\"Manage contact list to prevent hitting limits\"\"\"
        try:
            status = await self.get_contact_list_status()
""",
    """    async def manage_contact_list(self, auto_cleanup: bool = True) -> dict:
        \"\"\"Manage contact list to prevent hitting limits\"\"\"
        import time as _time
        quiet_until = getattr(self, '_capacity_quiet_until', 0.0)
        if auto_cleanup and _time.time() < quiet_until:
            return {'actions_taken': [], 'success': True, 'skipped': 'nothing to remove last time'}
        try:
            status = await self.get_contact_list_status()
""",
)

patch(
    "modules/repeater_manager.py",
    """            # Log the management action
            if actions_taken:
                self.log_purging_action(
                    "contact_management",
                    f'Contact list management: {"; ".join(actions_taken)}',
                )
""",
    """            # Log the management action
            if actions_taken:
                self._capacity_quiet_until = 0.0
                self.log_purging_action(
                    "contact_management",
                    f'Contact list management: {"; ".join(actions_taken)}',
                )
            elif auto_cleanup and status.get('is_near_limit'):
                # Nothing could be removed (with "overwrite oldest" the radio manages a full list itself):
                # do not repeat this for every new contact.
                self._capacity_quiet_until = _time.time() + 6 * 3600
                self.logger.info("Contact list: nothing to remove, next capacity check in 6 hours")
""",
)
