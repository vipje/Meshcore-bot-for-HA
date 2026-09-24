"""Contact cleanup service plugin.

The radio has a fixed number of contact slots. This service keeps some room free
by trimming the contact list when it gets too full: at `trigger_at` contacts it
removes the oldest unused ones until `target` contacts are left.

Never removed:
  - contacts starred in the web dashboard,
  - favourites on the radio,
  - the room server the bot logs in to, admins and the bot's protected keys,
  - contacts that were active in the last `keep_days` days.

Removing a contact from the radio does not remove it from the bot database, so
it stays on the dashboard map.

Second, independent job: once a week every contact that has gone silent is removed
from the radio, whatever the fill level: repeaters after `stale_repeater_days` days
(default 14) and all other contacts (companions, room servers, sensors) after
`stale_other_days` days (default 30; 0 leaves them alone). Companions do not advert
by themselves, so their last-seen time only moves when they send something, which is
why they get a longer limit. Same exclusions as above. Contacts with no known
last-seen time are left alone.

Both are also available on demand through the admin command `cleanup`.

Third job (when `[Bot] protect_starred` is on): every 30 minutes, contacts starred in the
dashboard get the favourite mark on the radio. Without it the firmware's "overwrite the
oldest non-favourite" policy can overwrite a starred contact that has been quiet for a few
days; the bot's own sync only runs once, shortly after start.

Config (config.ini):

    [ContactCleanup]
    enabled = true
    trigger_at = 300
    target = 250
    keep_days = 7
    stale_enabled = true
    stale_repeater_days = 14
    stale_other_days = 30
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from .base_service import BaseServicePlugin

_CHECK_INTERVAL_SECONDS = 30 * 60
_STARTUP_DELAY_SECONDS = 5 * 60   # after the bot's own favourite passes (90 s / 180 s)
_STALE_CHECK_INTERVAL_SECONDS = 6 * 60 * 60   # is the weekly run due?
_STALE_RUN_EVERY_SECONDS = 7 * 86400
_STALE_META_KEY = "contactcleanup.last_stale_run"
_MAX_REMOVALS_PER_RUN = 100
_DELAY_BETWEEN_REMOVALS = 2.0     # be gentle with the radio and the mesh


def contact_recency(contact: dict) -> int:
    """Last time we saw anything of this contact (0 = unknown = oldest)."""
    values = []
    for key in ("lastmod", "last_advert"):
        try:
            values.append(int(contact.get(key) or 0))
        except (TypeError, ValueError):
            pass
    return max(values) if values else 0


def plan_cleanup(
    contacts: dict,
    protected: set,
    target: int,
    keep_days: int,
    now: Optional[float] = None,
    is_repeater=lambda c: c.get("type") in (2, 3, 4),
    limit: int = _MAX_REMOVALS_PER_RUN,
) -> list:
    """Return the contacts to remove, in removal order (may be empty)."""
    now = time.time() if now is None else now
    need = len(contacts) - target
    if need <= 0:
        return []
    cutoff = now - keep_days * 86400
    candidates = []
    for key, contact in contacts.items():
        pub = (contact.get("public_key") or key or "").lower()
        try:
            flags = int(contact.get("flags") or 0)
        except (TypeError, ValueError):
            flags = 0
        if pub in protected or (flags & 1):
            continue
        recency = contact_recency(contact)
        if recency > cutoff:
            continue
        candidates.append((0 if is_repeater(contact) else 1, recency, pub, contact))
    # Infrastructure nodes that have gone quiet go first, then quiet companions;
    # within each group the one not heard for longest goes first.
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [item[3] for item in candidates[: min(need, limit)]]


def describe_contacts(contacts: dict, protected: set, keep_days: int, now: Optional[float] = None) -> dict:
    """Why a cleanup may have nothing to do: how many are protected, recent, and how old the rest is."""
    now = time.time() if now is None else now
    n_protected = n_recent = n_unknown = 0
    oldest = 0.0
    for key, contact in contacts.items():
        pub = (contact.get("public_key") or key or "").lower()
        try:
            flags = int(contact.get("flags") or 0)
        except (TypeError, ValueError):
            flags = 0
        if pub in protected or (flags & 1):
            n_protected += 1
            continue
        recency = contact_recency(contact)
        if recency <= 0:
            n_unknown += 1
            continue
        age_days = (now - recency) / 86400
        oldest = max(oldest, age_days)
        if age_days < keep_days:
            n_recent += 1
    return {"protected": n_protected, "recent": n_recent, "unknown_age": n_unknown, "oldest_days": round(oldest, 1)}


def plan_stale_contacts(
    contacts: dict,
    protected: set,
    repeater_days: int,
    other_days: int,
    now: Optional[float] = None,
    limit: int = _MAX_REMOVALS_PER_RUN,
) -> list:
    """Contacts that have been silent too long, longest silent first.

    Repeaters (type 2) use `repeater_days`, everything else `other_days`
    (0 = never remove those).
    """
    now = time.time() if now is None else now
    stale = []
    for key, contact in contacts.items():
        days = repeater_days if contact.get("type") == 2 else other_days
        if not days or days <= 0:
            continue
        pub = (contact.get("public_key") or key or "").lower()
        try:
            flags = int(contact.get("flags") or 0)
        except (TypeError, ValueError):
            flags = 0
        if pub in protected or (flags & 1):
            continue
        recency = contact_recency(contact)
        if recency <= 0 or recency >= now - days * 86400:   # unknown or recent: leave it
            continue
        stale.append((recency, contact))
    stale.sort(key=lambda item: item[0])
    return [c for _, c in stale[:limit]]


class ContactCleanupService(BaseServicePlugin):
    config_section = "ContactCleanup"

    # Settings card on the dashboard's Plugins page (the add-on options for this moved here in 2.7.0).
    settings_schema = [
        {"key": "trigger_at", "label": "Clean up when the radio holds this many contacts", "type": "int",
         "default": 300, "min": 20, "max": 1000,
         "help": "Checked every 30 minutes. The oldest unused contacts go until the target is reached."},
        {"key": "target", "label": "Clean up down to", "type": "int", "default": 250, "min": 10, "max": 990,
         "help": "Must be lower than the number above."},
        {"key": "keep_days", "label": "Never remove contacts active within", "type": "int", "default": 7,
         "min": 0, "max": 365, "unit": "days",
         "help": ("Starred contacts, radio favourites, the room server, admins and recently active contacts are "
                  "never removed. Removed contacts stay on the dashboard map.")},
        {"key": "stale_enabled", "label": "Weekly removal of silent contacts", "type": "bool", "default": False,
         "help": "Once a week, whatever the fill level, contacts that have been silent for too long are removed."},
        {"key": "stale_repeater_days", "label": "Repeaters silent for more than", "type": "int", "default": 14,
         "min": 2, "max": 365, "unit": "days"},
        {"key": "stale_other_days", "label": "Other contacts silent for more than", "type": "int", "default": 30,
         "min": 0, "max": 365, "unit": "days", "help": "0 = never remove other contacts this way."},
    ]
    description = "Trims the radio's contact list when it is nearly full, never touching starred or protected contacts"

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        section = self.config_section
        has = cfg.has_section(section)
        self.cleanup_enabled = cfg.getboolean(section, "enabled", fallback=False) if has else False
        self.trigger_at = cfg.getint(section, "trigger_at", fallback=300) if has else 300
        self.target = cfg.getint(section, "target", fallback=250) if has else 250
        self.keep_days = cfg.getint(section, "keep_days", fallback=7) if has else 7
        self.protect_starred = cfg.getboolean("Bot", "protect_starred", fallback=False)
        self.stale_enabled = cfg.getboolean(section, "stale_enabled", fallback=False) if has else False
        self.stale_repeater_days = cfg.getint(section, "stale_repeater_days", fallback=14) if has else 14
        self.stale_other_days = cfg.getint(section, "stale_other_days", fallback=30) if has else 30
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self.last_result: dict = {}

    # ---- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        self.enabled = True  # stays loaded: the 'cleanup' command uses it
        if self.cleanup_enabled and self.target >= self.trigger_at:
            self.logger.warning(
                "ContactCleanup: target (%s) moet lager zijn dan trigger_at (%s), opschonen op aantal uit",
                self.target, self.trigger_at,
            )
            self.cleanup_enabled = False
        if not (self.cleanup_enabled or self.stale_enabled or self.protect_starred):
            self.logger.debug("ContactCleanup: niets te doen (alles uit)")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(_STARTUP_DELAY_SECONDS)
        next_count_check = 0.0
        while self._running:
            try:
                now = time.time()
                if getattr(self.bot, "connected", False):
                    if self.protect_starred:
                        await self._sync_favourites()
                    contacts = getattr(getattr(self.bot, "meshcore", None), "contacts", None) or {}
                    if self.cleanup_enabled and now >= next_count_check:
                        next_count_check = now + _CHECK_INTERVAL_SECONDS
                        if len(contacts) >= self.trigger_at:
                            await self.run(dry_run=False, reason="automatic")
                    if self.stale_enabled and self._stale_due(now):
                        await self.run_stale(dry_run=False, reason="weekly")
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning("ContactCleanup: fout tijdens opschonen: %s", e, exc_info=True)
            await asyncio.sleep(min(_CHECK_INTERVAL_SECONDS, _STALE_CHECK_INTERVAL_SECONDS))

    async def _sync_favourites(self) -> None:
        """Give starred contacts the favourite mark on the radio (idempotent, only changes what is missing)."""
        rm = getattr(self.bot, "repeater_manager", None)
        sync = getattr(rm, "sync_device_mode_favourites_pass1", None)
        if sync is None:
            return
        try:
            await sync()
        except Exception as e:  # noqa: BLE001
            self.logger.debug("ContactCleanup: favorieten synchroniseren mislukt: %s", e)

    def _stale_due(self, now: float) -> bool:
        try:
            last = float(self.bot.db_manager.get_metadata(_STALE_META_KEY) or 0)
        except (TypeError, ValueError):
            last = 0.0
        return now - last >= _STALE_RUN_EVERY_SECONDS

    # ---- logic -----------------------------------------------------------
    def _protected_keys(self) -> set:
        protected: set = set()
        cfg = self.bot.config
        # Starred in the dashboard: always excluded here, whatever protect_starred says.
        try:
            rows = self.bot.db_manager.execute_query(
                "SELECT public_key FROM complete_contact_tracking WHERE is_starred = 1"
            )
            protected |= {(r["public_key"] or "").lower() for r in rows if r["public_key"]}
        except Exception as e:  # noqa: BLE001
            self.logger.debug("ContactCleanup: kon sterren niet lezen: %s", e)
        # Admins, announcement ACL and other keys the bot itself protects.
        try:
            from modules.repeater_manager import collect_protected_pubkeys_for_device_mode
            protected |= {k.lower() for k in collect_protected_pubkeys_for_device_mode(cfg, self.logger)}
        except Exception as e:  # noqa: BLE001
            self.logger.debug("ContactCleanup: kon beschermde sleutels niet lezen: %s", e)
        for key in cfg.get("Admin_ACL", "admin_pubkeys", fallback="").split(","):
            if key.strip():
                protected.add(key.strip().lower())
        room_key = cfg.get("RoomServer_Login", "public_key", fallback="").strip().lower()
        if room_key:
            protected.add(room_key)
        return protected

    def plan(self, target: Optional[int] = None) -> list:
        contacts = dict(getattr(getattr(self.bot, "meshcore", None), "contacts", None) or {})
        repeater_manager = getattr(self.bot, "repeater_manager", None)
        is_repeater = (
            repeater_manager._is_repeater_device if repeater_manager is not None
            else (lambda c: c.get("type") in (2, 3, 4))
        )
        return plan_cleanup(
            contacts, self._protected_keys(), target if target is not None else self.target,
            self.keep_days, is_repeater=is_repeater,
        )

    async def run(self, dry_run: bool = True, reason: str = "manual", target: Optional[int] = None) -> dict:
        """Plan and (unless dry_run) perform a cleanup. Returns a summary dict."""
        async with self._lock:
            contacts = getattr(getattr(self.bot, "meshcore", None), "contacts", None) or {}
            before = len(contacts)
            wanted = target if target is not None else self.target
            planned = self.plan(wanted)
            names = [c.get("adv_name") or c.get("name") or (c.get("public_key") or "?")[:8] for c in planned]
            result = {
                "before": before, "target": wanted, "planned": len(planned),
                "names": names, "removed": 0, "dry_run": dry_run,
                "info": describe_contacts(dict(contacts), self._protected_keys(), self.keep_days),
            }
            if dry_run or not planned:
                self.last_result = result
                return result

            await self._remove(planned, names, reason, result)
            result["after"] = len(getattr(self.bot.meshcore, "contacts", None) or {})
            self.logger.info(
                "ContactCleanup klaar: %s verwijderd, nu %s contacten", result["removed"], result["after"]
            )
            self.last_result = result
            return result

    async def _remove(self, planned: list, names: list, reason: str, result: dict) -> None:
        rm = self.bot.repeater_manager
        for i, contact in enumerate(planned):
            pub = contact.get("public_key") or ""
            name = names[i]
            try:
                if rm._is_repeater_device(contact):
                    ok = await rm.purge_repeater_from_contacts(pub, f"Contact cleanup ({reason})")
                else:
                    ok = await rm.purge_companion_from_contacts(pub, f"Contact cleanup ({reason})")
                if ok:
                    result["removed"] += 1
                    self.logger.info("ContactCleanup: %s van de radio verwijderd (blijft op de kaart)", name)
                else:
                    self.logger.warning("ContactCleanup: %s niet verwijderd", name)
            except Exception as e:  # noqa: BLE001
                self.logger.warning("ContactCleanup: fout bij %s: %s", name, e)
            if i < len(planned) - 1:
                await asyncio.sleep(_DELAY_BETWEEN_REMOVALS)

    async def run_stale(self, dry_run: bool = True, reason: str = "manual") -> dict:
        """Remove contacts that have been silent too long (unless dry_run)."""
        async with self._lock:
            contacts = dict(getattr(getattr(self.bot, "meshcore", None), "contacts", None) or {})
            planned = plan_stale_contacts(
                contacts, self._protected_keys(), self.stale_repeater_days, self.stale_other_days
            )
            names = [c.get("adv_name") or c.get("name") or (c.get("public_key") or "?")[:8] for c in planned]
            result = {
                "before": len(contacts), "repeater_days": self.stale_repeater_days,
                "other_days": self.stale_other_days, "planned": len(planned),
                "names": names, "removed": 0, "dry_run": dry_run, "stale": True,
                "info": describe_contacts(contacts, self._protected_keys(), 0),
            }
            if not dry_run:
                if planned:
                    self.logger.info(
                        "ContactCleanup (%s): %s stille contacten (repeaters >%s d, overige >%s d)",
                        reason, len(planned), self.stale_repeater_days, self.stale_other_days,
                    )
                    await self._remove(planned, names, reason, result)
                result["after"] = len(getattr(self.bot.meshcore, "contacts", None) or {})
                try:
                    self.bot.db_manager.set_metadata(_STALE_META_KEY, str(time.time()))
                except Exception as e:  # noqa: BLE001
                    self.logger.debug("ContactCleanup: kon laatste run niet opslaan: %s", e)
            self.last_result = result
            return result
