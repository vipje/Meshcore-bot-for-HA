#!/usr/bin/env python3
"""Shared helpers for the community commands (dx, karma, checkin, prikbord, herinner, voorspel, xp, badge, ...).

- Who is a bot: the same rules as the greeter and the channel hint (modules/channel_hint.py: robot emoji or the word
  bot in the name, plus the hand-made lists of the Bots page), and the bot itself. Rankings leave bots out.
- Days are counted in the bot's own timezone (Europe/Amsterdam unless [Bot] timezone says otherwise), so a check-in
  at 00:30 counts for the new day there, not in UTC.
- The tables these commands keep are created here, in the bot's own database, next to upstream's tables (which are
  only ever read).

People are recognised by the name they use on the mesh (a channel message carries nothing else). Anything that must
not be faked by someone taking over a name (the prediction game, reminders) uses the public key, which only a direct
message carries.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

try:
    import pytz
except ImportError:  # pragma: no cover
    pytz = None  # type: ignore[assignment]

DEFAULT_TZ = "Europe/Amsterdam"


# ---------------------------------------------------------------------------------------------------- who is a bot
def own_name(bot: Any) -> str:
    try:
        return (bot.config.get("Bot", "bot_name", fallback="") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def is_bot_name(bot: Any, name: str) -> bool:
    """True for another bot (Bots page rules) and for this bot itself."""
    name = (name or "").strip()
    if not name:
        return False
    if name.lower() == own_name(bot).lower():
        return True
    try:
        from .channel_hint import get_channel_hint
        return bool(get_channel_hint(bot).classify(name)[0])
    except Exception:  # noqa: BLE001  (no Bots settings available: only the plain name rules)
        lowered = name.lower()
        return "🤖" in name or bool(re.search(r"(^|[^a-z])bot([^a-z]|$)", lowered))


def without_bots(bot: Any, rows: Iterable, limit: int, name_index: int = 0) -> list:
    """The first `limit` rows whose name (row[name_index]) is not a bot."""
    out = []
    for row in rows:
        if is_bot_name(bot, row[name_index]):
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------------------------------- time
def tz(bot: Any):
    name = DEFAULT_TZ
    try:
        name = (bot.config.get("Bot", "timezone", fallback="") or "").strip() or DEFAULT_TZ
    except Exception:  # noqa: BLE001
        pass
    if pytz is None:
        return None
    try:
        return pytz.timezone(name)
    except Exception:  # noqa: BLE001
        return pytz.timezone(DEFAULT_TZ)


def _localize(zone, naive: datetime) -> datetime:
    return zone.localize(naive) if zone is not None and hasattr(zone, "localize") else naive.astimezone()


def local_now(bot: Any, now_ts: Optional[float] = None) -> datetime:
    return datetime.fromtimestamp(time.time() if now_ts is None else now_ts, tz(bot))


def local_day(bot: Any, now_ts: Optional[float] = None) -> date:
    return local_now(bot, now_ts).date()


def day_start_ts(bot: Any, day: date) -> int:
    return int(_localize(tz(bot), datetime(day.year, day.month, day.day)).timestamp())


def week_start_ts(bot: Any, now_ts: Optional[float] = None) -> int:
    """Monday 00:00 of this week, local time."""
    today = local_day(bot, now_ts)
    return day_start_ts(bot, today - timedelta(days=today.weekday()))


def month_start_ts(bot: Any, now_ts: Optional[float] = None) -> int:
    today = local_day(bot, now_ts)
    return day_start_ts(bot, today.replace(day=1))


_DURATION_RE = re.compile(r"^(\d{1,4})\s*(m|min|u|h|d)$", re.IGNORECASE)
_CLOCK_RE = re.compile(r"^([01]?\d|2[0-3])[:.]([0-5]\d)$")
_UNIT_S = {"m": 60, "min": 60, "u": 3600, "h": 3600, "d": 86400}


def parse_when(token: str, bot: Any, now_ts: Optional[float] = None) -> Optional[int]:
    """'30m', '2u'/'2h', '1d' or a clock time '18:30' (today, or tomorrow when already past) -> unix time, else None."""
    now_ts = time.time() if now_ts is None else now_ts
    token = (token or "").strip().lower()
    m = _DURATION_RE.match(token)
    if m:
        return int(now_ts + int(m.group(1)) * _UNIT_S[m.group(2)])
    m = _CLOCK_RE.match(token)
    if m:
        today = local_day(bot, now_ts)
        for day in (today, today + timedelta(days=1)):
            at = _localize(tz(bot), datetime(day.year, day.month, day.day, int(m.group(1)), int(m.group(2))))
            if at.timestamp() > now_ts:
                return int(at.timestamp())
    return None


def streaks(days: list, today: date) -> tuple:
    """(current streak, best streak) from a list of ISO dates. Current counts when the last day is today or yesterday."""
    ds = sorted({date.fromisoformat(d) for d in days})
    best = run = 0
    prev = None
    for d in ds:
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    current = run if ds and (today - ds[-1]).days <= 1 else 0
    return current, best


# ---------------------------------------------------------------------------------------------------- text
def fit_bytes(text: str, max_bytes: int, ellipsis: str = "…") -> str:
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    cut = data[: max(0, max_bytes - len(ellipsis.encode("utf-8")))].decode("utf-8", "ignore").rstrip()
    return cut + ellipsis


def pack_lines(header: str, items: list, max_bytes: int, sep: str = " | ") -> list:
    """Put `items` after `header` in as few messages of `max_bytes` as possible."""
    chunks, cur = [], header
    for item in items:
        joiner = " " if cur == header else sep
        candidate = f"{cur}{joiner}{item}"
        if len(candidate.encode("utf-8")) <= max_bytes:
            cur = candidate
        else:
            chunks.append(cur)
            cur = fit_bytes(item, max_bytes)
    if cur:
        chunks.append(cur)
    return chunks


def split_args(command: Any, message: Any) -> str:
    """The text after the command word (prefix and keyword removed)."""
    try:
        _kw, args = command.split_trigger_and_args(message.content or "")
        return (args or "").strip()
    except Exception:  # noqa: BLE001
        parts = (message.content or "").strip().split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""


# ---------------------------------------------------------------------------------------------------- replies
REPLY_BY_DM_FIELD = {
    "key": "reply_by_dm", "label": "Answer by direct message", "type": "bool", "default": True,
    "help": ("Asked in a channel: the answer goes as a direct message to the one who asked, so the channel stays quiet. "
             "When that fails (the sender is not in the bot's contacts) the answer comes in the channel after all."),
}


async def reply_private(command: Any, message: Any, text: str) -> bool:
    """Send `text` to the asker by DM when the command's reply_by_dm is on and the question came from a channel;
    fall back to the channel when the DM cannot be sent."""
    if getattr(message, "is_dm", False) or not getattr(command, "reply_by_dm", False):
        return await command.send_response(message, text)
    recipient = getattr(message, "sender_pubkey", None) or getattr(message, "sender_id", None)
    ok = False
    if recipient:
        try:
            ok = await command.bot.command_manager.send_dm(recipient, text)
        except Exception as e:  # noqa: BLE001
            command.logger.debug(f"{command.name}: DM to {recipient} failed: {e}")
    if ok:
        return True
    command.logger.info(f"{command.name}: DM to {getattr(message, 'sender_id', '?')} not possible, answering in the channel")
    return await command.send_response(message, text)


# ---------------------------------------------------------------------------------------------------- tables
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS community_karma (
        id INTEGER PRIMARY KEY AUTOINCREMENT, giver TEXT NOT NULL, receiver TEXT NOT NULL,
        day TEXT NOT NULL, ts INTEGER NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_community_karma_receiver ON community_karma(receiver)",
    """CREATE TABLE IF NOT EXISTS community_checkin (
        name TEXT NOT NULL, day TEXT NOT NULL, ts INTEGER NOT NULL, PRIMARY KEY (name, day))""",
    """CREATE TABLE IF NOT EXISTS community_board (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, text TEXT NOT NULL,
        created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS community_reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, pubkey TEXT NOT NULL, name TEXT, text TEXT NOT NULL,
        due_at INTEGER NOT NULL, created_at INTEGER NOT NULL, tries INTEGER NOT NULL DEFAULT 0,
        next_try INTEGER NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS community_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, creator TEXT NOT NULL, creator_name TEXT, question TEXT NOT NULL,
        options TEXT NOT NULL, state TEXT NOT NULL, answer INTEGER, created_at INTEGER NOT NULL, closed_at INTEGER)""",
    """CREATE TABLE IF NOT EXISTS community_answers (
        question_id INTEGER NOT NULL, pubkey TEXT NOT NULL, name TEXT, choice INTEGER NOT NULL, ts INTEGER NOT NULL,
        PRIMARY KEY (question_id, pubkey))""",
]


def ensure_tables(db: Any) -> None:
    with db.connection() as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()


def table_exists(conn: Any, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None
