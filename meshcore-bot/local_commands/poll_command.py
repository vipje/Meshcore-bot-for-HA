#!/usr/bin/env python3
"""
'stem'/'poll' command for the MeshCore Bot.
Quick yes/no vote on a channel, max 1 active poll per channel. Voting is
silent per-vote except for a short tally ack; use 'stem uitslag' to see the
current count, or 'stem stop' to end early and announce the final tally.
No automatic end-of-duration announcement in this version - the poll simply
stops accepting votes once its TTL passes (known simplification).

Duration is adjustable per poll via an optional leading '<N>m' (minutes),
'<N>h' (hours) or '<N>d' (days) token - exactly one of the three, not
combined (no '1h30m') - e.g. 'stem 15m pizza vanavond?' or 'stem 1d ...'.
Defaults to 10 minutes when omitted, clamped to 1 minute..1 day either way
so a poll can't be started for (say) a week and then forgotten about.
"""

import re
from typing import Any

from ..channel_session import ChannelSession
from ..models import MeshMessage
from .base_command import BaseCommand

_DURATION_RE = re.compile(r"^(\d+)([mhd])$")
_UNIT_SECONDS = {"m": 60, "h": 60 * 60, "d": 24 * 60 * 60}
_UNIT_KEY = {"m": "commands.poll.unit_min", "h": "commands.poll.unit_hour", "d": "commands.poll.unit_day"}
_MIN_POLL_SECONDS = 60
_MAX_POLL_SECONDS = 24 * 60 * 60
_DEFAULT_POLL_SECONDS = 10 * 60


def _parse_duration(rest: str, translate) -> tuple[int, str, str]:
    """Extract an optional leading '<N>m'/'<N>h'/'<N>d' duration from `rest`.

    Returns (seconds, display_label, remaining_text). Falls back to the
    10-minute default (and leaves `rest` untouched) when there's no leading
    duration token, so 'stem <vraag>' with no duration keeps working exactly
    as before.
    """
    first, _, remainder = rest.partition(" ")
    match = _DURATION_RE.match(first)
    if not match:
        return _DEFAULT_POLL_SECONDS, translate("commands.poll.unit_min", n=10), rest

    value, unit = int(match.group(1)), match.group(2)
    raw_seconds = value * _UNIT_SECONDS[unit]
    seconds = max(_MIN_POLL_SECONDS, min(_MAX_POLL_SECONDS, raw_seconds))

    shown = seconds // _UNIT_SECONDS[unit]
    key = _UNIT_KEY[unit] if unit != "d" or shown == 1 else "commands.poll.unit_days"
    label = translate(key, n=shown)

    return seconds, label, remainder.strip()


class PollCommand(BaseCommand):
    """Quick yes/no channel poll, one active per channel at a time."""

    name = "poll"
    keywords = ["stem", "poll", "ja", "nee"]
    description = "Ja/nee-stemming op een kanaal (usage: stem [Nm|Nd] <vraag>, dan ja/nee)"
    category = "fun"

    short_description = "Ja/nee-stemming"
    usage = "stem [Nm|Nh|Nd] <vraag>"
    examples = ["stem pizza vanavond?", "stem 15m pizza vanavond?", "stem 2h wie kookt?", "stem 1d wie kookt?", "stem uitslag", "stem stop"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.poll_enabled = self.get_config_value(
            "Poll_Command", "enabled", fallback=True, value_type="bool"
        )
        self._sessions = ChannelSession()

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.poll_enabled:
            return False
        # Bare "ja"/"nee" only count as votes while a poll is actually
        # running on this channel - otherwise this command stays invisible
        # and doesn't clash with any other meaning those words might have.
        first_word = message.content.strip().lower().split(" ", 1)[0] if message.content else ""
        if first_word in ("ja", "nee") and not self._sessions.is_active(message.channel):
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return (
            "Start een ja/nee-stemming: 'stem <vraag>' (vraag max ~80 tekens, "
            "anders past het bericht niet). Optioneel een duur ervoor (precies "
            "één van de drie, niet combineren): 'stem 15m <vraag>', "
            "'stem 2h <vraag>' of 'stem 1d <vraag>' (standaard 10 min, max 1 dag). "
            "Anderen stemmen met 'ja'/'nee'. 'stem uitslag' toont de tussenstand, "
            "'stem stop' beëindigt de stemming vroegtijdig."
        )

    @staticmethod
    def _tally(votes: dict) -> tuple[int, int]:
        ja = sum(1 for v in votes.values() if v)
        nee = sum(1 for v in votes.values() if not v)
        return ja, nee

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip()
            lower = content.lower()
            channel = message.channel

            first_word = lower.split(" ", 1)[0] if lower else ""

            if first_word in ("ja", "nee"):
                session = self._sessions.get(channel)
                if session is None:
                    return True  # No active poll - stay silent (see can_execute).
                session["votes"][message.sender_id or "onbekend"] = (first_word == "ja")
                ja, nee = self._tally(session["votes"])
                return await self.send_response(message, self.translate("commands.poll.vote_recorded", ja=ja, nee=nee))

            # 'stem'/'poll' prefix - strip it to get the sub-command/question.
            for prefix in ("stem", "poll"):
                if lower.startswith(prefix):
                    rest = content[len(prefix):].strip()
                    break
            else:
                rest = content
            rest_lower = rest.lower()

            if rest_lower == "uitslag":
                session = self._sessions.get(channel)
                if session is None:
                    return await self.send_response(message, self.translate("commands.poll.no_active"))
                ja, nee = self._tally(session["votes"])
                return await self.send_response(
                    message, self.translate("commands.poll.tally", question=session["question"], ja=ja, nee=nee)
                )

            if rest_lower in ("stop", "einde"):
                session = self._sessions.get(channel)
                if session is None:
                    return await self.send_response(message, self.translate("commands.poll.no_active_to_stop"))
                ja, nee = self._tally(session["votes"])
                self._sessions.end(channel)
                return await self.send_response(
                    message, self.translate("commands.poll.ended", question=session["question"], ja=ja, nee=nee)
                )

            if not rest:
                return await self.send_response(message, self.translate("commands.poll.usage"))

            if self._sessions.is_active(channel):
                return await self.send_response(
                    message, self.translate("commands.poll.already_active")
                )

            duration_seconds, duration_label, question = _parse_duration(rest, self.translate)
            if not question:
                return await self.send_response(message, self.translate("commands.poll.usage"))

            # The "Stemming gestart: '<vraag>' - stem met ja/nee (<duur>)"
            # wrapper below is the longest of the three templates this
            # question gets embedded in (start/uitslag/stop) - if it fits
            # here it fits in the other two as well. Checked here rather
            # than left to whatever sends the message, which was silently
            # truncating mid-word instead of failing loudly (a general fix
            # for that now also exists at the send layer itself - see
            # local_patches/patch_channel_message_length_guard.py - but
            # rejecting up front here still gives a clearer error than
            # having it auto-split into two messages).
            max_total = self.get_max_message_length(message)
            max_question_bytes = max(20, max_total - 55)
            if len(question.encode("utf-8")) > max_question_bytes:
                return await self.send_response(
                    message,
                    self.translate("commands.poll.question_too_long", max=max_question_bytes),
                )

            self._sessions.start(channel, {"question": question, "votes": {}}, duration_seconds)
            return await self.send_response(
                message, self.translate("commands.poll.started", question=question, duration=duration_label)
            )
        except Exception as e:
            self.logger.error(f"Error executing poll command: {e}")
            return await self.send_response(message, self.translate("commands.poll.error", error=str(e)))
