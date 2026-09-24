#!/usr/bin/env python3
"""
'voorspel' command for the MeshCore Bot: a prediction game for any question (like the F1 game, but for anything).

  voorspel                         the open question, the choices and (by DM) your own answer
  voorspel nieuw <vraag> | a | b [| ... tot 6]   start a question (DM; one open question at a time)
  voorspel <nummer>                your answer (DM; can be changed until the question is closed)
  voorspel sluit                   stop taking answers (DM, only the one who asked)
  voorspel uitslag <nummer>        the right answer: 1 point for everyone who had it (DM, only the one who asked)
  voorspel stand                   the points, top 5

Asking and answering go by direct message only: that carries the public key, so nobody can answer for someone
else or settle someone else's question. The key is stored in the bot's database and never shown; rankings show
the name the person had when they last answered. Viewing (the question, the standings) also works in a channel.
"""

import json
import time
from typing import Any, Optional

from ..mesh_community import ensure_tables, fit_bytes, pack_lines, split_args
from ..models import MeshMessage
from .base_command import BaseCommand

NEW = {"nieuw", "new", "neu", "nouveau", "start"}
CLOSE = {"sluit", "close", "dicht"}
RESULT = {"uitslag", "result", "antwoord"}
STANDINGS = {"stand", "punten", "top", "standings"}
MAX_CHOICES = 6


class VoorspelCommand(BaseCommand):
    """Prediction game for any question: ask, answer by DM, points for the right answer."""

    name = "voorspel"
    keywords = ["voorspel"]
    description = "Voorspellingsspel voor elke vraag: voorspel nieuw <vraag> | a | b, antwoorden met voorspel <nr> (DM)"
    category = "games"

    short_description = "Voorspellingsspel voor elke vraag"
    usage = "voorspel [nieuw <vraag> | a | b|<nr>|sluit|uitslag <nr>|stand]"
    examples = ["voorspel", "voorspel nieuw Wordt het zaterdag droog? | ja | nee", "voorspel 1", "voorspel stand"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.voorspel_enabled = self.get_config_value("Voorspel_Command", "enabled", fallback=True, value_type="bool")
        self._ready = False

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.voorspel_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.voorspel.help")

    def _db(self):
        if not self._ready:
            ensure_tables(self.bot.db_manager)
            self._ready = True
        return self.bot.db_manager.connection()

    @staticmethod
    def _current(conn) -> Optional[tuple]:
        """(id, creator, question, [choices], state) of the question that is open or closed-but-not-settled."""
        row = conn.execute("SELECT id, creator, question, options, state FROM community_questions WHERE state IN ('open', 'closed') ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        return row[0], row[1], row[2], json.loads(row[3]), row[4]

    @staticmethod
    def _choices_text(choices: list) -> str:
        return " ".join(f"{i}) {c}" for i, c in enumerate(choices, 1))

    # ------------------------------------------------------------------ actions
    def show(self, pubkey: str, max_bytes: int) -> str:
        with self._db() as conn:
            q = self._current(conn)
            if not q:
                return self.translate("commands.voorspel.none")
            qid, _creator, question, choices, state = q
            n = conn.execute("SELECT COUNT(*) FROM community_answers WHERE question_id=?", (qid,)).fetchone()[0]
            mine = conn.execute("SELECT choice FROM community_answers WHERE question_id=? AND pubkey=?", (qid, (pubkey or "").lower())).fetchone()
        key = "commands.voorspel.show_open" if state == "open" else "commands.voorspel.show_closed"
        text = self.translate(key, question=question, choices=self._choices_text(choices), n=n)
        if mine:
            text += " " + self.translate("commands.voorspel.yours", choice=mine[0] + 1)
        return fit_bytes(text, max_bytes)

    def create(self, pubkey: str, name: str, args: str, now_ts: float) -> str:
        parts = [p.strip() for p in args.split("|")]
        question, choices = parts[0], [p for p in parts[1:] if p]
        if not question or not 2 <= len(choices) <= MAX_CHOICES:
            return self.translate("commands.voorspel.new_usage", max=MAX_CHOICES)
        with self._db() as conn:
            if self._current(conn):
                return self.translate("commands.voorspel.busy")
            cur = conn.execute("INSERT INTO community_questions (creator, creator_name, question, options, state, created_at) VALUES (?,?,?,?,?,?)",
                               (pubkey, name, question, json.dumps(choices, ensure_ascii=False), "open", int(now_ts)))
            conn.commit()
        return self.translate("commands.voorspel.created", id=cur.lastrowid)

    def answer(self, pubkey: str, name: str, number: int, now_ts: float) -> str:
        with self._db() as conn:
            q = self._current(conn)
            if not q:
                return self.translate("commands.voorspel.none")
            qid, _c, _question, choices, state = q
            if state != "open":
                return self.translate("commands.voorspel.closed")
            if not 1 <= number <= len(choices):
                return self.translate("commands.voorspel.bad_choice", max=len(choices))
            conn.execute("INSERT OR REPLACE INTO community_answers (question_id, pubkey, name, choice, ts) VALUES (?,?,?,?,?)",
                         (qid, pubkey, name, number - 1, int(now_ts)))
            conn.commit()
        return self.translate("commands.voorspel.answered", choice=number, text=choices[number - 1])

    def close(self, pubkey: str, now_ts: float) -> str:
        with self._db() as conn:
            q = self._current(conn)
            if not q:
                return self.translate("commands.voorspel.none")
            if q[1] != pubkey:
                return self.translate("commands.voorspel.not_owner")
            conn.execute("UPDATE community_questions SET state='closed', closed_at=? WHERE id=?", (int(now_ts), q[0]))
            conn.commit()
            n = conn.execute("SELECT COUNT(*) FROM community_answers WHERE question_id=?", (q[0],)).fetchone()[0]
        return self.translate("commands.voorspel.closed_now", n=n)

    def settle(self, pubkey: str, number: int, now_ts: float, max_bytes: int) -> str:
        with self._db() as conn:
            q = self._current(conn)
            if not q:
                return self.translate("commands.voorspel.none")
            qid, creator, question, choices, _state = q
            if creator != pubkey:
                return self.translate("commands.voorspel.not_owner")
            if not 1 <= number <= len(choices):
                return self.translate("commands.voorspel.bad_choice", max=len(choices))
            conn.execute("UPDATE community_questions SET state='settled', answer=?, closed_at=COALESCE(closed_at, ?) WHERE id=?",
                         (number - 1, int(now_ts), qid))
            conn.commit()
            right = [r[0] for r in conn.execute("SELECT name FROM community_answers WHERE question_id=? AND choice=? ORDER BY ts", (qid, number - 1)).fetchall()]
            total = conn.execute("SELECT COUNT(*) FROM community_answers WHERE question_id=?", (qid,)).fetchone()[0]
        names = ", ".join(right[:6]) + ("…" if len(right) > 6 else "") if right else "-"
        return fit_bytes(self.translate("commands.voorspel.settled", answer=choices[number - 1], good=len(right), total=total, names=names), max_bytes)

    def standings(self, max_bytes: int) -> list:
        with self._db() as conn:
            rows = conn.execute(
                """SELECT a.pubkey, COUNT(*) FROM community_answers a JOIN community_questions q ON q.id = a.question_id
                   WHERE q.state='settled' AND a.choice = q.answer GROUP BY a.pubkey ORDER BY COUNT(*) DESC LIMIT 5""").fetchall()
            out = []
            for pubkey, points in rows:
                name = conn.execute("SELECT name FROM community_answers WHERE pubkey=? ORDER BY ts DESC LIMIT 1", (pubkey,)).fetchone()
                out.append(f"{len(out) + 1}. {(name[0] if name and name[0] else '?')} {points}")
        if not out:
            return [self.translate("commands.voorspel.no_points")]
        return pack_lines(self.translate("commands.voorspel.standings_header"), out, max_bytes)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            args = split_args(self, message)
            words = args.split()
            word = words[0].lower() if words else ""
            pubkey = (message.sender_pubkey or "").lower()
            name = message.sender_id or ""
            max_bytes = self.get_max_message_length(message)
            now = time.time()

            if not words:
                return await self.send_response(message, self.show(pubkey if message.is_dm else "", max_bytes))
            if word in STANDINGS:
                chunks = self.standings(max_bytes)
                return await (self.send_response(message, chunks[0]) if len(chunks) == 1 else self.send_response_chunked(message, chunks[:2]))
            if not message.is_dm or not pubkey:
                return await self.send_response(message, self.translate("commands.voorspel.dm_only"))
            if word in NEW:
                return await self.send_response(message, self.create(pubkey, name, args[len(words[0]):].strip(), now))
            if word in CLOSE:
                return await self.send_response(message, self.close(pubkey, now))
            if word in RESULT and len(words) == 2 and words[1].isdigit():
                return await self.send_response(message, self.settle(pubkey, int(words[1]), now, max_bytes))
            if word.isdigit():
                return await self.send_response(message, self.answer(pubkey, name, int(word), now))
            return await self.send_response(message, self.translate("commands.voorspel.help"))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing voorspel command: {e}")
            return await self.send_response(message, self.translate("commands.voorspel.error", error=str(e)))
