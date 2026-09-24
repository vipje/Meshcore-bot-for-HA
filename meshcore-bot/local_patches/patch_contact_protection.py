#!/usr/bin/env python3
"""Source patch applied to the vendored meshcore-bot repeater manager.

Runs once during the Docker build (see patch_webviewer.py for the shared
rationale/mechanics).

Problems in v1.0.0 this fixes:

1. The star in the web dashboard (complete_contact_tracking.is_starred) only
   influences path inference. Nothing stops the contact-limit management from
   removing a starred repeater/companion from the radio. With
   [Bot] protect_starred = true (default here) starred contacts are never
   removed from the radio by the bot: not by auto-purge, not by the
   stale-contact cleanup, not by manual purge commands. They are also favourited
   on the radio, so the firmware's "overwrite oldest non-favourite" policy
   leaves them alone too.

2. sync_device_mode_favourites_pass2() clears the favourite bit of every
   contact that is not in the bot's protected set, about three minutes after
   every start. That silently removes stars a user set in the MeshCore app.
   With [Bot] keep_radio_favourites = true that pass is skipped.

Contacts removed from the radio stay in the bot database, so they remain on
the dashboard map; this patch only stops removals, it never deletes map data.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()
FILE = "modules/repeater_manager.py"


def patch(old: str, new: str) -> None:
    p = ROOT / FILE
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {FILE} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {FILE}")


# 1. Helpers, placed right before the repeater candidate selection.
patch(
    """    async def _get_repeaters_for_purging(self, count: int) -> list[dict]:""",
    '''    def _starred_public_keys(self) -> set:
        """Public keys (lowercase) starred in the web dashboard."""
        if not self.bot.config.getboolean('Bot', 'protect_starred', fallback=False):
            return set()
        try:
            rows = self.db_manager.execute_query(
                'SELECT public_key FROM complete_contact_tracking WHERE is_starred = 1'
            )
            return {(r['public_key'] or '').lower() for r in rows if r['public_key']}
        except Exception as e:
            self.logger.debug('Could not read starred contacts: %s', e)
            return set()

    def _is_starred_protected(self, public_key: str) -> bool:
        key = (public_key or '').lower()
        return bool(key) and key in self._starred_public_keys()

    async def _get_repeaters_for_purging(self, count: int) -> list[dict]:''',
)

# 2. Candidate selection: never pick starred contacts.
patch(
    """            for contact_key, contact_data in list(self.bot.meshcore.contacts.items()):
                # Check if this is a repeater device
                if self._is_repeater_device(contact_data):""",
    """            starred = self._starred_public_keys()
            for contact_key, contact_data in list(self.bot.meshcore.contacts.items()):
                if (contact_data.get('public_key', contact_key) or '').lower() in starred:
                    continue
                # Check if this is a repeater device
                if self._is_repeater_device(contact_data):""",
)
patch(
    """            for contact_key, contact_data in list(self.bot.meshcore.contacts.items()):
                # Check if this is a companion device
                if not self._is_companion_device(contact_data):
                    continue
""",
    """            starred = self._starred_public_keys()
            for contact_key, contact_data in list(self.bot.meshcore.contacts.items()):
                if (contact_data.get('public_key', contact_key) or '').lower() in starred:
                    continue
                # Check if this is a companion device
                if not self._is_companion_device(contact_data):
                    continue
""",
)

# 3. Hard guards on every removal path.
patch(
    '''        """Remove a specific repeater from the device's contact list using proper MeshCore API"""
        if not self._start_purge_attempt(public_key, "repeater"):''',
    '''        """Remove a specific repeater from the device's contact list using proper MeshCore API"""
        if self._is_starred_protected(public_key):
            self.logger.info("Not removing %s from the radio: starred in the dashboard", public_key[:16])
            return False
        if not self._start_purge_attempt(public_key, "repeater"):''',
)
patch(
    '''        """Remove a companion contact from the device's contact list"""
        if not self._start_purge_attempt(public_key, "companion"):''',
    '''        """Remove a companion contact from the device's contact list"""
        if self._is_starred_protected(public_key):
            self.logger.info("Not removing %s from the radio: starred in the dashboard", public_key[:16])
            return False
        if not self._start_purge_attempt(public_key, "companion"):''',
)
patch(
    '''        """Remove a repeater using the contact key (public_key hex) from the device's contact list"""
        self.logger.info(f"Starting purge process for contact_key: {contact_key}")''',
    '''        """Remove a repeater using the contact key (public_key hex) from the device's contact list"""
        if self._is_starred_protected(contact_key):
            self.logger.info("Not removing %s from the radio: starred in the dashboard", contact_key[:16])
            return False
        self.logger.info(f"Starting purge process for contact_key: {contact_key}")''',
)
patch(
    """            for contact in stale_contacts[:max_remove]:""",
    """            starred = self._starred_public_keys()
            stale_contacts = [c for c in stale_contacts if (c.get('public_key') or '').lower() not in starred]
            for contact in stale_contacts[:max_remove]:""",
)

# 4. Favourite bit on the radio: dashboard stars get it, app stars are kept.
patch(
    """        protected = collect_protected_pubkeys_for_device_mode(self.bot.config, self.logger)
        if not protected:
            self.logger.debug('sync_device_mode_favourites_pass1: no protected pubkeys configured')""",
    """        protected = set(collect_protected_pubkeys_for_device_mode(self.bot.config, self.logger))
        protected |= self._starred_public_keys()
        if not protected:
            self.logger.debug('sync_device_mode_favourites_pass1: no protected pubkeys configured')""",
)
patch(
    """        protected = collect_protected_pubkeys_for_device_mode(self.bot.config, self.logger)
        spacing_ms = max(0, self.bot.config.getint('Bot', 'contact_flag_update_spacing_ms', fallback=200))
        spacing = spacing_ms / 1000.0
        try:
            await self.bot.meshcore.commands.get_contacts()
        except Exception as e:
            self.logger.debug('get_contacts before favourite pass2: %s', e)""",
    """        if self.bot.config.getboolean('Bot', 'keep_radio_favourites', fallback=False):
            self.logger.info('keep_radio_favourites: favourites set in the app are left as they are')
            return
        protected = set(collect_protected_pubkeys_for_device_mode(self.bot.config, self.logger))
        protected |= self._starred_public_keys()
        spacing_ms = max(0, self.bot.config.getint('Bot', 'contact_flag_update_spacing_ms', fallback=200))
        spacing = spacing_ms / 1000.0
        try:
            await self.bot.meshcore.commands.get_contacts()
        except Exception as e:
            self.logger.debug('get_contacts before favourite pass2: %s', e)""",
)
