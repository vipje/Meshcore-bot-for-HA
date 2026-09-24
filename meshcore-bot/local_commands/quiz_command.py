#!/usr/bin/env python3
"""
'quiz' command for the MeshCore Bot.
One multiple-choice trivia question per channel at a time, via the free
OpenTDB API (no key required). English-only (no reliable Dutch trivia API
found) - accepted limitation.
"""

import html
import random
from typing import Any

import aiohttp

from ..channel_session import ChannelSession
from ..models import MeshMessage
from .base_command import BaseCommand

_OPENTDB_URL = "https://opentdb.com/api.php"
_ANSWER_TTL_SECONDS = 60
_LETTERS = ["a", "b", "c", "d"]


class QuizCommand(BaseCommand):
    """One active multiple-choice trivia question per channel."""

    name = "quiz"
    keywords = ["quiz"]
    description = "Kort multiple-choice vraagje (usage: quiz, dan quiz a/b/c/d)"
    category = "fun"
    requires_internet = True

    short_description = "Multiple-choice trivia"
    usage = "quiz"
    examples = ["quiz", "quiz a"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.quiz_enabled = self.get_config_value(
            "Quiz_Command", "enabled", fallback=True, value_type="bool"
        )
        self._sessions = ChannelSession()

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.quiz_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return (
            "Stuurt een multiple-choice trivia-vraag. Antwoord binnen 60s met "
            "'quiz a', 'quiz b', 'quiz c' of 'quiz d'. Engelstalige vragen."
        )

    async def _fetch_question(self) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _OPENTDB_URL,
                params={"amount": 1, "type": "multiple"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
        results = data.get("results") or []
        if not results:
            raise ValueError(self.translate("commands.quiz.no_question"))
        return results[0]

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip().lower()
            channel = message.channel
            answer_word = content[len("quiz"):].strip() if content.startswith("quiz") else content

            active = self._sessions.get(channel)

            # Answering an active question.
            if active and answer_word in _LETTERS:
                if answer_word == active["correct_letter"]:
                    result = self.translate(
                        "commands.quiz.correct",
                        letter=active["correct_letter"].upper(), answer=active["correct_answer"],
                    )
                else:
                    result = self.translate(
                        "commands.quiz.wrong",
                        given=answer_word.upper(), letter=active["correct_letter"].upper(),
                        answer=active["correct_answer"],
                    )
                self._sessions.end(channel)
                return await self.send_response(message, result)

            if active:
                return await self.send_response(
                    message, self.translate("commands.quiz.already_active")
                )

            # Starting a new question.
            question_data = await self._fetch_question()
            question = html.unescape(question_data["question"])
            correct_answer = html.unescape(question_data["correct_answer"])
            options = [html.unescape(a) for a in question_data["incorrect_answers"]] + [correct_answer]
            random.shuffle(options)
            correct_letter = _LETTERS[options.index(correct_answer)]

            self._sessions.start(
                channel,
                {"correct_letter": correct_letter, "correct_answer": correct_answer},
                _ANSWER_TTL_SECONDS,
            )

            option_lines = [f"{_LETTERS[i].upper()}) {opt}" for i, opt in enumerate(options)]
            response = (
                self.translate("commands.quiz.question", question=question)
                + " | " + " | ".join(option_lines)
                + " | " + self.translate("commands.quiz.answer_hint")
            )
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing quiz command: {e}")
            return await self.send_response(message, self.translate("commands.quiz.error", error=str(e)))
