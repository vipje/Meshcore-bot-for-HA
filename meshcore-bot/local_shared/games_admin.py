#!/usr/bin/env python3
"""Backend of the dashboard's Games page (see local_web/games.html and patch_webviewer_games.py).

One read-only overview of every game on the mesh: Mesh RPG (xp), DX Jacht (dx), karma, check-in streaks, the open
voorspel question and the F1 prediction game. Everything comes from the tables the commands and the Community
service keep (modules/mesh_archive.py, modules/mesh_community.py, modules/f1_game.py); this module only reads, apart
from creating those tables when they do not exist yet. Bots (the Bots page rules, and the bot itself) are left out
of every ranking. Public keys are never sent to the browser.

This runs inside the web viewer process, which has its own DBManager and config but no bot object, so the helpers
get a small stand-in with `config`, `db_manager` and `logger` (like bots_admin.py).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Optional

from modules.mesh_archive import (BADGES, CMD_CAP, DX_HOP_CAP, MSG_CAP, XP_CHECKIN, XP_CMD, XP_HOP, XP_KARMA, XP_MSG, badges_of, dx_best,
                                  ensure_archive, known_names, month_start_day, week_start_day, xp_of)
from modules.mesh_community import is_bot_name, local_day, local_now, streaks, table_exists, without_bots

TOP = 15


def _bot(db_manager: Any, config: Any, logger: Optional[logging.Logger]) -> Any:
    return SimpleNamespace(config=config, db_manager=db_manager, logger=logger or logging.getLogger("games_admin"))


def _dx(bot: Any, since_day: Optional[str]) -> list:
    rows = without_bots(bot, dx_best(bot, since_day), TOP)
    return [{"name": n, "hops": h, "date": local_now(bot, t).strftime("%d-%m-%Y")} for n, h, t in rows]


def xp_parts(info: dict) -> list:
    """Where someone's XP comes from, in the order the page shows it; the xp values add up to info['xp']."""
    return [
        {"key": "messages", "count": info["messages"], "per": XP_MSG, "xp": info["messages"] * XP_MSG, "cap": MSG_CAP},
        {"key": "commands", "count": info["commands"], "per": XP_CMD, "xp": info["commands"] * XP_CMD, "cap": CMD_CAP},
        {"key": "checkins", "count": info["checkins"], "per": XP_CHECKIN, "xp": info["checkins"] * XP_CHECKIN},
        {"key": "karma", "count": info["karma"], "per": XP_KARMA, "xp": info["karma"] * XP_KARMA},
        {"key": "dx", "count": info["best_hops"], "per": XP_HOP, "xp": min(info["best_hops"], DX_HOP_CAP) * XP_HOP, "cap": DX_HOP_CAP},
    ]


def _xp(bot: Any, since_day: Optional[str], with_details: bool) -> list:
    scores = []
    for name in known_names(bot, since_day):
        if is_bot_name(bot, name):
            continue
        info = xp_of(bot, name, since_day)
        if info["xp"] > 0:
            scores.append((name, info))
    scores.sort(key=lambda r: (-r[1]["xp"], r[0].lower()))
    out = []
    for name, info in scores[:TOP]:
        row = {"name": name, "xp": info["xp"], "parts": xp_parts(info),
               "active_days": info["active_days"], "all_messages": info["all_messages"]}
        if with_details:
            row.update({"level": info["level"], "title": info["title"], "next": info["next"],
                        "badges": badges_of(bot, name)})
        out.append(row)
    return out


def _karma(bot: Any, conn: Any) -> list:
    rows = conn.execute("SELECT receiver, COUNT(*) AS n FROM community_karma GROUP BY LOWER(receiver) ORDER BY n DESC, MIN(ts) LIMIT 60").fetchall()
    return [{"name": n, "points": p} for n, p in without_bots(bot, rows, TOP)]


def _checkin(bot: Any, conn: Any) -> list:
    today = local_day(bot)
    per: dict = {}
    for name, day in conn.execute("SELECT name, day FROM community_checkin WHERE day >= ?", ((today - timedelta(days=400)).isoformat(),)):
        per.setdefault(name.lower(), [name, []])[1].append(day)
    rows = []
    for name, days in per.values():
        current, best = streaks(days, today)
        if current > 0:
            rows.append((name, current, best))
    rows.sort(key=lambda r: (-r[1], -r[2], r[0].lower()))
    return [{"name": n, "streak": c, "best": b} for n, c, b in without_bots(bot, rows, TOP)]


def _voorspel(bot: Any, conn: Any) -> dict:
    out: dict = {"question": None, "standings": []}
    row = conn.execute("SELECT id, question, options, state, creator_name FROM community_questions WHERE state IN ('open', 'closed') ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        qid, question, options, state, creator = row
        choices = json.loads(options)
        counts = [0] * len(choices)
        for (choice,) in conn.execute("SELECT choice FROM community_answers WHERE question_id=?", (qid,)):
            if 0 <= choice < len(counts):
                counts[choice] += 1
        out["question"] = {"text": question, "state": state, "asked_by": creator or "",
                           "choices": [{"text": c, "answers": n} for c, n in zip(choices, counts)]}
    rows = conn.execute(
        """SELECT a.pubkey, COUNT(*) FROM community_answers a JOIN community_questions q ON q.id = a.question_id
           WHERE q.state='settled' AND a.choice = q.answer GROUP BY a.pubkey ORDER BY COUNT(*) DESC LIMIT 60""").fetchall()
    named = []
    for pubkey, points in rows:
        name = conn.execute("SELECT name FROM community_answers WHERE pubkey=? ORDER BY ts DESC LIMIT 1", (pubkey,)).fetchone()
        named.append(((name[0] if name and name[0] else "?"), points))
    out["standings"] = [{"name": n, "points": p} for n, p in without_bots(bot, named, TOP)]
    return out


def _f1_open(bot: Any, conn: Any) -> Optional[dict]:
    """The latest round with predictions but no points yet: who has predicted (the picks stay hidden until scoring)."""
    row = conn.execute(
        """SELECT p.season, p.round FROM f1_predictions p WHERE NOT EXISTS
           (SELECT 1 FROM f1_points s WHERE s.season = p.season AND s.round = p.round)
           ORDER BY p.season DESC, CAST(p.round AS INTEGER) DESC LIMIT 1""").fetchone()
    if not row:
        return None
    season, rnd = row
    names = [(n or "?",) for (n,) in conn.execute(
        "SELECT name FROM f1_predictions WHERE season=? AND round=? ORDER BY created_at", (season, rnd)).fetchall()]
    names = [n for (n,) in without_bots(bot, names, 60)]
    return {"season": season, "round": rnd, "names": names} if names else None


def _f1(bot: Any, conn: Any) -> dict:
    if not table_exists(conn, "f1_predictions") or not table_exists(conn, "f1_points"):
        return {"season": None, "standings": [], "open": None}
    open_round = _f1_open(bot, conn)
    season = conn.execute("SELECT MAX(season) FROM f1_points").fetchone()[0]
    if not season:
        return {"season": open_round["season"] if open_round else None, "standings": [], "open": open_round}
    rows = conn.execute("SELECT pubkey, SUM(points), COUNT(*) FROM f1_points WHERE season=? GROUP BY pubkey ORDER BY SUM(points) DESC LIMIT 60",
                        (season,)).fetchall()
    named = []
    for pubkey, points, races in rows:
        name = conn.execute("SELECT name FROM f1_predictions WHERE pubkey=? AND season=? ORDER BY created_at DESC LIMIT 1",
                            (pubkey, season)).fetchone()
        named.append(((name[0] if name and name[0] else "?"), int(points), int(races)))
    return {"season": season, "standings": [{"name": n, "points": p, "races": r} for n, p, r in without_bots(bot, named, TOP)],
            "open": open_round}


def standings(db_manager: Any, config: Any, logger: Optional[logging.Logger] = None) -> dict:
    """Everything the Games page shows, bots left out."""
    bot = _bot(db_manager, config, logger)
    ensure_archive(db_manager)
    week, month = week_start_day(bot), month_start_day(bot)
    with db_manager.connection() as conn:
        karma, checkin = _karma(bot, conn), _checkin(bot, conn)
        voorspel, f1 = _voorspel(bot, conn), _f1(bot, conn)
        last_day = conn.execute("SELECT MAX(day) FROM community_activity").fetchone()[0]
    return {
        "generated_at": int(time.time()),
        "last_activity_day": last_day,
        "badges_total": len(BADGES),
        "xp": {"ever": _xp(bot, None, True), "week": _xp(bot, week, False)},
        "dx": {"week": _dx(bot, week), "month": _dx(bot, month), "ever": _dx(bot, None)},
        "karma": karma,
        "checkin": checkin,
        "voorspel": voorspel,
        "f1": f1,
    }
