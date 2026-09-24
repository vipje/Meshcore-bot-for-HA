#!/usr/bin/env python3
"""The F1 prediction game: pick the winner of the next race, points after the race (see f1_service.py).

Who plays is decided by the sender's public key, which only a direct message carries and which cannot be faked,
so nobody can vote for someone else. A channel message only has a display name and is never accepted. The key is
stored in the bot's database and never shown; standings show the name the person had when they last played.

Rules: one pick per race (a new pick replaces the old one until the lock), the pick can be changed until the
first qualifying session of the weekend starts. Points: the winner picked right = 5, a pick that finished second
or third = 2, anything else = 0.
"""
from __future__ import annotations

from typing import Any, Optional

POINTS_WINNER = 5
POINTS_PODIUM = 2


class F1Game:
    def __init__(self, db_manager: Any):
        self.db = db_manager

    def ensure_tables(self) -> None:
        with self.db.connection() as conn:
            cur = conn.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS f1_predictions (
                season TEXT NOT NULL, round TEXT NOT NULL, pubkey TEXT NOT NULL, name TEXT, pick TEXT NOT NULL,
                created_at INTEGER NOT NULL, PRIMARY KEY (season, round, pubkey))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS f1_points (
                season TEXT NOT NULL, round TEXT NOT NULL, pubkey TEXT NOT NULL, name TEXT, pick TEXT, points INTEGER NOT NULL,
                PRIMARY KEY (season, round, pubkey))""")
            conn.commit()

    # ------------------------------------------------------------------ playing
    def predict(self, season: str, rnd: str, pubkey: str, name: str, code: str, now_ts: float,
                lock_ts: Optional[float], valid_codes: set, translate) -> tuple:
        """(ok, message in the sender's detected language). Codes are the 3-letter driver codes of this season."""
        code = (code or "").strip().upper()
        if not pubkey:
            return False, translate("commands.f1.predict_no_key")
        if lock_ts is not None and now_ts >= lock_ts:
            return False, translate("commands.f1.predict_locked")
        if valid_codes and code not in valid_codes:
            return False, translate("commands.f1.predict_unknown_code", code=code or "?", example=sorted(valid_codes)[0])
        if not code or len(code) != 3:
            return False, translate("commands.f1.predict_bad_format")
        with self.db.connection() as conn:
            cur = conn.cursor()
            previous = cur.execute("SELECT pick FROM f1_predictions WHERE season=? AND round=? AND pubkey=?", (season, rnd, pubkey.lower())).fetchone()
            cur.execute("INSERT OR REPLACE INTO f1_predictions (season, round, pubkey, name, pick, created_at) VALUES (?,?,?,?,?,?)",
                        (season, rnd, pubkey.lower(), name or "", code, int(now_ts)))
            conn.commit()
        if previous and previous[0] != code:
            return True, translate("commands.f1.predict_changed", code=code, previous=previous[0])
        return True, translate("commands.f1.predict_recorded", code=code)

    def pick_of(self, season: str, rnd: str, pubkey: str) -> Optional[str]:
        with self.db.connection() as conn:
            row = conn.execute("SELECT pick FROM f1_predictions WHERE season=? AND round=? AND pubkey=?", (season, rnd, (pubkey or "").lower())).fetchone()
        return row[0] if row else None

    def players(self, season: str, rnd: str) -> int:
        with self.db.connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM f1_predictions WHERE season=? AND round=?", (season, rnd)).fetchone()[0]

    # ------------------------------------------------------------------ scoring
    def score(self, season: str, rnd: str, results: list) -> list:
        """Give points for one finished race, once. Returns [(name, pick, points)] best first; [] if already scored."""
        podium = {r["pos"]: r["code"] for r in results if r["pos"] in ("1", "2", "3")}
        winner = podium.get("1")
        with self.db.connection() as conn:
            cur = conn.cursor()
            if cur.execute("SELECT 1 FROM f1_points WHERE season=? AND round=? LIMIT 1", (season, rnd)).fetchone():
                return []
            rows = cur.execute("SELECT pubkey, name, pick FROM f1_predictions WHERE season=? AND round=?", (season, rnd)).fetchall()
            scored = []
            for pubkey, name, pick in rows:
                pts = POINTS_WINNER if pick == winner else (POINTS_PODIUM if pick in (podium.get("2"), podium.get("3")) else 0)
                cur.execute("INSERT INTO f1_points (season, round, pubkey, name, pick, points) VALUES (?,?,?,?,?,?)",
                            (season, rnd, pubkey, name, pick, pts))
                scored.append((name or "?", pick, pts))
            conn.commit()
        return sorted(scored, key=lambda s: (-s[2], s[0].lower()))

    def standings(self, season: str, limit: int = 5) -> list:
        """[(name, points, races)] for the season, best first (the latest name of each player)."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT pubkey, SUM(points), COUNT(*) FROM f1_points WHERE season=? GROUP BY pubkey ORDER BY SUM(points) DESC LIMIT ?",
                (season, max(1, limit) * 3)).fetchall()
            out = []
            for pubkey, total, races in rows:
                name = conn.execute("SELECT name FROM f1_predictions WHERE pubkey=? AND season=? ORDER BY created_at DESC, CAST(round AS INTEGER) DESC LIMIT 1", (pubkey, season)).fetchone()
                out.append(((name[0] if name and name[0] else "?"), int(total), int(races)))
        return sorted(out, key=lambda r: (-r[1], r[0].lower()))[:limit]

    def points_of(self, season: str, pubkey: str) -> tuple:
        with self.db.connection() as conn:
            row = conn.execute("SELECT COALESCE(SUM(points),0), COUNT(*) FROM f1_points WHERE season=? AND pubkey=?", (season, (pubkey or "").lower())).fetchone()
        return int(row[0]), int(row[1])
