#!/usr/bin/env python3
"""A lasting archive of who did what per day, for DX Jacht ('dx') and Mesh RPG ('xp', 'badge').

Upstream keeps its statistics (message_stats, command_stats, path_stats) only [Stats_Command] data_retention_days
days, 7 by default. Records "of all time" and XP that keeps growing need more, so this module copies a summary per
person per local day into two tables of our own, and only ever reads upstream's tables:

  community_activity (name, day, messages, commands)   how many messages and bot commands someone sent that day
  community_dx       (name, day, hops, ts, path)        someone's message with the most hops that day

sync() reads the last 8 days of upstream's tables and writes those days again. A count only goes up (MAX of the old
and the new value), so a day that upstream is already clearing does not shrink here. The Community service calls
sync() every 10 minutes; the commands call it too (at most once a minute) so what they show is current.

Mesh RPG, all computed from the archive and the community tables, nothing stored:
  XP = messages (max 20 a day) + 2 x commands (max 10 a day) + 5 x check-ins + 10 x karma received + 5 x best hops
       (the best hops count up to 10, so at most 50 XP from DX)
  level L needs 25 x L x (L+1) XP (50, 150, 300, 500, ...); titles by level.
"""
from __future__ import annotations

import time
from datetime import timedelta
from typing import Any, Optional

from .mesh_community import ensure_tables, local_day, streaks, table_exists

SYNC_DAYS = 8
MIN_SYNC_GAP_S = 60
MSG_CAP, CMD_CAP = 20, 10
XP_MSG, XP_CMD, XP_CHECKIN, XP_KARMA, XP_HOP = 1, 2, 5, 10, 5
DX_HOP_CAP = 10   # the best DX counts for at most 10 hops (50 XP): one lucky far message must not outweigh weeks of taking part
TITLE_LEVELS = [(18, 6), (12, 5), (8, 4), (5, 3), (3, 2), (1, 1), (0, 0)]   # (from level, title number)

ARCHIVE_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS community_activity (
        name TEXT NOT NULL, day TEXT NOT NULL, messages INTEGER NOT NULL DEFAULT 0, commands INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (name, day))""",
    """CREATE TABLE IF NOT EXISTS community_dx (
        name TEXT NOT NULL, day TEXT NOT NULL, hops INTEGER NOT NULL, ts INTEGER NOT NULL, path TEXT,
        PRIMARY KEY (name, day))""",
    "CREATE INDEX IF NOT EXISTS idx_community_dx_day ON community_dx(day)",
]

_last_sync: dict = {}


def ensure_archive(db: Any) -> None:
    ensure_tables(db)
    with db.connection() as conn:
        for statement in ARCHIVE_SCHEMA:
            conn.execute(statement)
        conn.commit()


def sync(bot: Any, now_ts: Optional[float] = None, force: bool = False) -> bool:
    """Copy the last days of upstream's stats into the archive. Returns False when skipped (too soon)."""
    now_ts = time.time() if now_ts is None else now_ts
    key = id(bot.db_manager)
    if not force and now_ts - _last_sync.get(key, 0) < MIN_SYNC_GAP_S:
        return False
    _last_sync[key] = now_ts
    ensure_archive(bot.db_manager)
    since = int(now_ts - SYNC_DAYS * 86400)
    activity: dict = {}
    best: dict = {}
    with bot.db_manager.connection() as conn:
        if table_exists(conn, "message_stats"):
            for name, ts in conn.execute("SELECT sender_id, timestamp FROM message_stats WHERE timestamp >= ?", (since,)):
                if name:
                    k = (name, local_day(bot, ts).isoformat())
                    activity.setdefault(k, [0, 0])[0] += 1
        if table_exists(conn, "command_stats"):
            for name, ts in conn.execute("SELECT sender_id, timestamp FROM command_stats WHERE timestamp >= ?", (since,)):
                if name:
                    k = (name, local_day(bot, ts).isoformat())
                    activity.setdefault(k, [0, 0])[1] += 1
        if table_exists(conn, "path_stats"):
            for name, hops, ts, path in conn.execute(
                    "SELECT sender_id, hops, timestamp, path_string FROM path_stats WHERE timestamp >= ? AND hops > 0", (since,)):
                if name:
                    k = (name, local_day(bot, ts).isoformat())
                    if k not in best or hops > best[k][0] or (hops == best[k][0] and ts < best[k][1]):
                        best[k] = (int(hops), int(ts), path)
        conn.executemany(
            """INSERT INTO community_activity (name, day, messages, commands) VALUES (?,?,?,?)
               ON CONFLICT(name, day) DO UPDATE SET messages = MAX(messages, excluded.messages),
                                                    commands = MAX(commands, excluded.commands)""",
            [(n, d, m, c) for (n, d), (m, c) in activity.items()])
        conn.executemany(
            """INSERT INTO community_dx (name, day, hops, ts, path) VALUES (?,?,?,?,?)
               ON CONFLICT(name, day) DO UPDATE SET hops = excluded.hops, ts = excluded.ts, path = excluded.path
               WHERE excluded.hops > community_dx.hops""",
            [(n, d, h, t, p) for (n, d), (h, t, p) in best.items()])
        conn.commit()
    return True


# ------------------------------------------------------------------------------------------------ DX Jacht
def dx_best(bot: Any, since_day: Optional[str], name: Optional[str] = None, limit: int = 60) -> list:
    """[(name, hops, ts)] best first: each person's best since `since_day` (ISO date, None = ever)."""
    where, params = ["1=1"], []
    if since_day:
        where.append("day >= ?")
        params.append(since_day)
    if name:
        where.append("LOWER(name) = LOWER(?)")
        params.append(name)
    with bot.db_manager.connection() as conn:
        rows = conn.execute(
            f"""SELECT name, hops, ts FROM community_dx d WHERE {' AND '.join(where)}
                AND hops = (SELECT MAX(hops) FROM community_dx e WHERE LOWER(e.name) = LOWER(d.name) {'AND e.day >= ?' if since_day else ''})
                ORDER BY hops DESC, ts ASC LIMIT 400""",
            params + ([since_day] if since_day else [])).fetchall()
    seen, out = set(), []
    for n, h, t in rows:                      # one row per person (their first time at their best)
        if n.lower() in seen:
            continue
        seen.add(n.lower())
        out.append((n, h, t))
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------------------------------------ Mesh RPG
def level_for(xp: int) -> int:
    level = 0
    while xp >= 25 * (level + 1) * (level + 2):
        level += 1
    return level


def xp_for_level(level: int) -> int:
    return 25 * level * (level + 1)


def title_number(level: int) -> int:
    for start, number in TITLE_LEVELS:
        if level >= start:
            return number
    return 0


def _parts(conn, name: str, since_day: Optional[str]) -> dict:
    day_filter = " AND day >= ?" if since_day else ""
    p = [name] + ([since_day] if since_day else [])
    msgs, cmds, active = conn.execute(
        f"SELECT COALESCE(SUM(MIN(messages, {MSG_CAP})),0), COALESCE(SUM(MIN(commands, {CMD_CAP})),0), COUNT(*) FROM community_activity WHERE LOWER(name)=LOWER(?){day_filter}",
        p).fetchone()
    raw_msgs = conn.execute(f"SELECT COALESCE(SUM(messages),0) FROM community_activity WHERE LOWER(name)=LOWER(?){day_filter}", p).fetchone()[0]
    checkins = conn.execute(f"SELECT COUNT(*) FROM community_checkin WHERE LOWER(name)=LOWER(?){day_filter}", p).fetchone()[0]
    karma = conn.execute(f"SELECT COUNT(*) FROM community_karma WHERE LOWER(receiver)=LOWER(?){day_filter}", p).fetchone()[0]
    hops = conn.execute(f"SELECT COALESCE(MAX(hops),0) FROM community_dx WHERE LOWER(name)=LOWER(?){day_filter}", p).fetchone()[0]
    return {"messages": int(msgs), "commands": int(cmds), "active_days": int(active), "all_messages": int(raw_msgs),
            "checkins": int(checkins), "karma": int(karma), "best_hops": int(hops)}


def xp_of(bot: Any, name: str, since_day: Optional[str] = None) -> dict:
    """XP, level and the parts it is made of, for one name (since_day: only XP earned from that day)."""
    ensure_archive(bot.db_manager)
    with bot.db_manager.connection() as conn:
        parts = _parts(conn, name, since_day)
    xp = (parts["messages"] * XP_MSG + parts["commands"] * XP_CMD + parts["checkins"] * XP_CHECKIN
          + parts["karma"] * XP_KARMA + min(parts["best_hops"], DX_HOP_CAP) * XP_HOP)
    level = level_for(xp)
    return {**parts, "xp": xp, "level": level, "next": xp_for_level(level + 1), "title": title_number(level)}


def known_names(bot: Any, since_day: Optional[str] = None) -> list:
    """Every name with archived activity (since that day), one spelling per person."""
    ensure_archive(bot.db_manager)
    with bot.db_manager.connection() as conn:
        if since_day:
            rows = conn.execute("SELECT name FROM community_activity WHERE day >= ? GROUP BY LOWER(name)", (since_day,)).fetchall()
        else:
            rows = conn.execute("SELECT name FROM community_activity GROUP BY LOWER(name)").fetchall()
    return [r[0] for r in rows]


def week_start_day(bot: Any, now_ts: Optional[float] = None) -> str:
    today = local_day(bot, now_ts)
    return (today - timedelta(days=today.weekday())).isoformat()


def month_start_day(bot: Any, now_ts: Optional[float] = None) -> str:
    return local_day(bot, now_ts).replace(day=1).isoformat()


# ------------------------------------------------------------------------------------------------ badges
# (key, test) in the order they are shown. The texts are translation keys commands.badge.name.<key>.
BADGES = [
    ("msg100", lambda p, s: p["all_messages"] >= 100),
    ("msg1000", lambda p, s: p["all_messages"] >= 1000),
    ("days30", lambda p, s: p["active_days"] >= 30),
    ("days100", lambda p, s: p["active_days"] >= 100),
    ("hops3", lambda p, s: p["best_hops"] >= 3),
    ("hops6", lambda p, s: p["best_hops"] >= 6),
    ("streak7", lambda p, s: s >= 7),
    ("streak30", lambda p, s: s >= 30),
    ("karma10", lambda p, s: p["karma"] >= 10),
    ("level5", lambda p, s: p["level"] >= 5),
    ("level10", lambda p, s: p["level"] >= 10),
]


def badges_of(bot: Any, name: str) -> list:
    """Badge keys this name has earned."""
    info = xp_of(bot, name)
    with bot.db_manager.connection() as conn:
        days = [r[0] for r in conn.execute("SELECT day FROM community_checkin WHERE LOWER(name)=LOWER(?)", (name,)).fetchall()]
    best_streak = streaks(days, local_day(bot))[1] if days else 0
    return [key for key, test in BADGES if test(info, best_streak)]
