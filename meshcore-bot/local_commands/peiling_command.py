#!/usr/bin/env python3
"""
'peiling' command for the MeshCore Bot: a multiple-choice vote on a channel (the yes/no version is 'stem').

  peiling [15m|2u|1d] <vraag> | <keuze 1> | <keuze 2> [| ... tot 5 keuzes]
  kies <nummer>        vote (only while a peiling runs on this channel; a new vote replaces your old one)
  peiling uitslag      the count so far          peiling stop      end it now and show the result

One peiling per channel at a time, default 10 minutes, at most 1 day. Like 'stem', it lives in memory only: a
restart of the bot ends it. Votes are counted per name.
"""

import re
from typing import Any

from ..channel_session import ChannelSession
from ..mesh_community import fit_bytes, split_args
from ..models import MeshMessage
from .base_command import BaseCommand

_DURATION_RE = re.compile(r"^(\d+)(m|u|h|d)$", re.IGNORECASE)
_UNIT_S = {"m": 60, "u": 3600, "h": 3600, "d": 86400}
DEFAULT_S, MIN_S, MAX_S = 600, 60, 86400
MAX_CHOICES = 5
RESULT = {"uitslag", "stand", "result"}
STOP = {"stop", "einde", "end"}


def parse_poll(rest: str) -> tuple:
    """(seconds, question, [choices]) from '[duur] vraag | a | b ...'; choices == [] when the format is wrong."""
    seconds = DEFAULT_S
    first, _, remainder = rest.strip().partition(" ")
    m = _DURATION_RE.match(first)
    if m:
        seconds = max(MIN_S, min(MAX_S, int(m.group(1)) * _UNIT_S[m.group(2).lower()]))
        rest = remainder
    parts = [p.strip() for p in rest.split("|")]
    question, choices = parts[0], [p for p in parts[1:] if p]
    if not question or not 2 <= len(choices) <= MAX_CHOICES:
        return seconds, question, []
    return seconds, question, choices


def duration_text(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}u"
    return f"{seconds // 60}m"


class PeilingCommand(BaseCommand):
    """Multiple-choice channel vote (2-5 choices), vote with 'kies <nummer>'."""

    name = "peiling"
    keywords = ["peiling", "kies"]
    description = "Meerkeuze-peiling op een kanaal: peiling [duur] vraag | a | b | c, stemmen met kies <nr>"
    category = "fun"

    short_description = "Meerkeuze-peiling (stem met kies <nr>)"
    usage = "peiling [Nm|Nu|Nd] <vraag> | <keuze> | <keuze> ..."
    examples = ["peiling Waar eten we? | pizza | friet | chinees", "peiling 1u Beste antenne? | 5 dBi | 8 dBi", "kies 2", "peiling uitslag", "peiling stop"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.peiling_enabled = self.get_config_value("Peiling_Command", "enabled", fallback=True, value_type="bool")
        self._sessions = ChannelSession()

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.peiling_enabled:
            return False
        # 'kies' only means something while a peiling runs on this channel; otherwise the bot stays silent.
        first = (message.content or "").strip().lstrip("!/").split(" ", 1)[0].lower()
        if first == "kies" and not self._sessions.is_active(self._key(message)):
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.peiling.help", max=MAX_CHOICES)

    @staticmethod
    def _key(message: MeshMessage) -> str:
        return message.channel or f"dm:{message.sender_id}"

    @staticmethod
    def _counts(session: dict) -> list:
        counts = [0] * len(session["choices"])
        for choice in session["votes"].values():
            counts[choice] += 1
        return counts

    def _result(self, session: dict, key: str, max_bytes: int) -> str:
        counts = self._counts(session)
        parts = [f"{c} {n}" for c, n in zip(session["choices"], counts)]
        return fit_bytes(self.translate(key, question=session["question"], result=" | ".join(parts), total=sum(counts)), max_bytes)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            key = self._key(message)
            max_bytes = self.get_max_message_length(message)
            first = (message.content or "").strip().lstrip("!/").split(" ", 1)[0].lower()
            args = split_args(self, message)

            if first == "kies":
                session = self._sessions.get(key)
                if session is None:
                    return True
                n = int(args) if args.strip().isdigit() else 0
                if not 1 <= n <= len(session["choices"]):
                    return await self.send_response(message, self.translate("commands.peiling.bad_choice", max=len(session["choices"])))
                session["votes"][(message.sender_id or "?").lower()] = n - 1
                counts = self._counts(session)
                return await self.send_response(message, self.translate("commands.peiling.voted", choice=session["choices"][n - 1],
                                                                        counts="/".join(str(c) for c in counts)))

            word = args.lower()
            if word in RESULT or word in STOP:
                session = self._sessions.get(key)
                if session is None:
                    return await self.send_response(message, self.translate("commands.peiling.none"))
                if word in STOP:
                    self._sessions.end(key)
                    return await self.send_response(message, self._result(session, "commands.peiling.ended", max_bytes))
                return await self.send_response(message, self._result(session, "commands.peiling.tally", max_bytes))

            if not args:
                return await self.send_response(message, self.translate("commands.peiling.usage", max=MAX_CHOICES))
            if self._sessions.is_active(key):
                return await self.send_response(message, self.translate("commands.peiling.already"))
            seconds, question, choices = parse_poll(args)
            if not choices:
                return await self.send_response(message, self.translate("commands.peiling.usage", max=MAX_CHOICES))
            listing = " ".join(f"{i}) {c}" for i, c in enumerate(choices, 1))
            text = self.translate("commands.peiling.started", question=question, choices=listing, duration=duration_text(seconds))
            if len(text.encode("utf-8")) > max_bytes:
                return await self.send_response(message, self.translate("commands.peiling.too_long", max=max_bytes))
            self._sessions.start(key, {"question": question, "choices": choices, "votes": {}}, seconds)
            return await self.send_response(message, text)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing peiling command: {e}")
            return await self.send_response(message, self.translate("commands.peiling.error", error=str(e)))
