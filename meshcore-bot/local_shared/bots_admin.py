#!/usr/bin/env python3
"""Backend of the dashboard's Bots page (see local_web/bots.html and patch_webviewer_bots.py).

Lists every name the bot has heard (channel messages and adverts) with what the automatic rules
make of it, and lets an admin overrule that per name. The overrides are the same hand-made lists
the `botlist` command edits (bot_metadata, see channel_hint.py), so page and command always agree,
and the bot process picks a change up within LIST_TTL_SECONDS without a restart.

This runs inside the web viewer process, which has its own DBManager and config but no bot object,
so the ChannelHint it builds only needs `config`, `db_manager` and `logger`.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Optional

from modules.channel_hint import ChannelHint

MAX_ROWS = 1500
MAX_NAME_LENGTH = 40


def _hint(db_manager: Any, config: Any, logger: Optional[logging.Logger] = None) -> ChannelHint:
    bot = SimpleNamespace(config=config, db_manager=db_manager, logger=logger or logging.getLogger("bots_admin"))
    hint = ChannelHint(bot)
    hint._lists_at = -1e9   # always read the lists fresh: this object lives for one request
    return hint


def _row(hint: ChannelHint, name: str, source: str, count: int = 0, last: int = 0) -> dict:
    auto, reason = hint.classify_auto(name)
    manual = hint.manual_state(name)
    return {
        "name": name,
        "source": source,               # channel | contact | list
        "messages": count,
        "last_heard": last,             # unix seconds, 0 = unknown
        "auto": auto,
        "auto_reason": reason,
        "manual": manual,               # True / False / None (automatic)
        "is_bot": auto if manual is None else manual,
    }


def list_names(db_manager: Any, config: Any, logger: Optional[logging.Logger] = None) -> dict:
    """All heard names, newest first, plus the counters the page shows."""
    hint = _hint(db_manager, config, logger)
    own = (config.get("Bot", "bot_name", fallback="") or "").strip().lower()
    rows: dict = {}

    def add(name: Any, source: str, count: int, last: Any) -> None:
        name = " ".join(str(name or "").split())
        if not name or name.lower() == own:
            return
        key = name.lower()
        try:
            last = int(last or 0)
        except (TypeError, ValueError):
            last = 0
        if key in rows:
            r = rows[key]
            r["messages"] += count
            r["last_heard"] = max(r["last_heard"], last)
            if r["source"] != "channel" and source == "channel":
                r["source"] = "channel"
            return
        rows[key] = _row(hint, name, source, count, last)

    try:
        with db_manager.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT sender_id, COUNT(*), MAX(timestamp) FROM message_stats "
                "WHERE is_dm = 0 AND sender_id IS NOT NULL AND sender_id != '' "
                "GROUP BY sender_id ORDER BY MAX(timestamp) DESC LIMIT ?",
                (MAX_ROWS,),
            )
            for name, count, last in cur.fetchall():
                add(name, "channel", int(count or 0), last)
            # Adverts: bots that only advertise and never post in a channel (Echobot, ...).
            # Only names that look like a bot, or that an admin already touched, to keep the list short.
            cur.execute(
                "SELECT name, MAX(strftime('%s', last_heard)) FROM complete_contact_tracking "
                "WHERE name IS NOT NULL AND name != '' GROUP BY name ORDER BY MAX(last_heard) DESC LIMIT ?",
                (MAX_ROWS,),
            )
            for name, last in cur.fetchall():
                clean = " ".join(str(name or "").split())
                if clean and (hint.classify_auto(clean)[0] or hint.manual_state(clean) is not None):
                    add(clean, "contact", 0, last)
    except Exception as e:  # noqa: BLE001 - a missing table must not break the page
        (logger or logging.getLogger("bots_admin")).warning("Bots page: reading names failed: %s", e)

    marked, never = hint.manual_lists()
    for name in marked + never:
        if name.lower() not in rows and name.lower() != own:
            rows[name.lower()] = _row(hint, name, "list")

    out = sorted(rows.values(), key=lambda r: (-r["last_heard"], r["name"].lower()))
    return {
        "names": out,
        "total": len(out),
        "bots": sum(1 for r in out if r["is_bot"]),
        "by_hand": sum(1 for r in out if r["manual"] is not None),
    }


def set_bot(db_manager: Any, config: Any, name: str, is_bot: Optional[bool],
            logger: Optional[logging.Logger] = None) -> dict:
    """Tick (True) or untick (False) a name; None puts it back to automatic.

    Ticking the same as the automatic rules say removes the override instead of storing one, so the
    hand-made lists only hold real exceptions. Raises ValueError for a bad name or a full list."""
    name = " ".join((name or "").split())
    if not name or len(name) > MAX_NAME_LENGTH:
        raise ValueError("naam ontbreekt of is te lang")
    hint = _hint(db_manager, config, logger)
    auto = hint.classify_auto(name)[0]
    status = None if (is_bot is None or is_bot == auto) else bool(is_bot)
    hint.set_manual(name, status)
    return _row(_hint(db_manager, config, logger), name, "list")
