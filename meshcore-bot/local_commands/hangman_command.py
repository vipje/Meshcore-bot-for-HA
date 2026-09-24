#!/usr/bin/env python3
"""
'hangman' command for the MeshCore Bot.
Letter-guessing game, one active game per channel. Every action goes through
the 'hangman' keyword (start/guess/stop) rather than bare letters, to avoid
accidentally hijacking unrelated short messages on a keyword-driven bot.
"""

import random
from typing import Any

from ..channel_session import ChannelSession
from ..local_data.hangman_words import HANGMAN_WORDS
from ..models import MeshMessage
from .base_command import BaseCommand

_GAME_TTL_SECONDS = 10 * 60
_MAX_WRONG = 6


class HangmanCommand(BaseCommand):
    """Letter-guessing game, one active game per channel."""

    name = "hangman"
    keywords = ["hangman"]
    description = "Letterraadspel (usage: hangman start [categorie], hangman <letter>, hangman raad <woord>, hangman stop)"
    category = "fun"

    short_description = "Letterraadspel"
    usage = "hangman start [categorie]"
    examples = ["hangman start dieren", "hangman a", "hangman raad olifant", "hangman stop"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.hangman_enabled = self.get_config_value(
            "Hangman_Command", "enabled", fallback=True, value_type="bool"
        )
        self._sessions = ChannelSession()

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.hangman_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return (
            "Letterraadspel. 'hangman start [categorie]' begint een spel "
            f"(categorieën: {', '.join(HANGMAN_WORDS.keys())}). Raad met "
            "'hangman <letter>' of 'hangman raad <woord>'. 'hangman stop' stopt."
        )

    @staticmethod
    def _board(word: str, guessed: set) -> str:
        return " ".join(letter if letter in guessed else "_" for letter in word)

    def _status_line(self, session: dict) -> str:
        word = session["word"]
        guessed = session["guessed"]
        wrong = sorted(g for g in guessed if g not in word)
        wrong_count = len(wrong)
        board = self._board(word, guessed)
        if wrong:
            wrong_str = self.translate("commands.hangman.wrong_suffix", letters=", ".join(wrong), n=wrong_count, max=_MAX_WRONG)
        else:
            wrong_str = self.translate("commands.hangman.wrong_suffix_none", max=_MAX_WRONG)
        return f"{board}{wrong_str}"

    def _pick_word(self, category_hint: str) -> tuple[str, str]:
        category = category_hint.strip().lower()
        if category in HANGMAN_WORDS:
            words = HANGMAN_WORDS[category]
        else:
            category = random.choice(list(HANGMAN_WORDS.keys()))
            words = HANGMAN_WORDS[category]
        return random.choice(words), category

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip()
            lower = content.lower()
            channel = message.channel

            rest = content[len("hangman"):].strip() if lower.startswith("hangman") else content
            rest_lower = rest.lower()

            session = self._sessions.get(channel)

            if rest_lower == "stop":
                if session is None:
                    return await self.send_response(message, self.translate("commands.hangman.no_game_to_stop"))
                word = session["word"]
                self._sessions.end(channel)
                return await self.send_response(message, self.translate("commands.hangman.stopped", word=word))

            if rest_lower.startswith("start"):
                if session is not None:
                    return await self.send_response(
                        message, self.translate("commands.hangman.already_running", status=self._status_line(session))
                    )
                category_hint = rest[len("start"):].strip()
                word, category = self._pick_word(category_hint)
                new_session = {"word": word, "guessed": set(), "category": category}
                self._sessions.start(channel, new_session, _GAME_TTL_SECONDS)
                return await self.send_response(
                    message,
                    self.translate(
                        "commands.hangman.started", category=category, n=len(word), status=self._status_line(new_session)
                    ),
                )

            if rest_lower.startswith("raad "):
                if session is None:
                    return await self.send_response(message, self.translate("commands.hangman.no_game"))
                guess_word = rest_lower[len("raad "):].strip()
                if guess_word == session["word"]:
                    self._sessions.end(channel)
                    return await self.send_response(
                        message, self.translate("commands.hangman.correct_word", word=session["word"])
                    )
                session["guessed"].update(set(guess_word) & set(session["word"]))
                wrong_count = len({g for g in session["guessed"] if g not in session["word"]}) + 1
                if wrong_count >= _MAX_WRONG:
                    word = session["word"]
                    self._sessions.end(channel)
                    return await self.send_response(message, self.translate("commands.hangman.wrong_word", word=word))
                return await self.send_response(
                    message, self.translate("commands.hangman.not_quite", status=self._status_line(session))
                )

            if len(rest_lower) == 1 and rest_lower.isalpha():
                if session is None:
                    return await self.send_response(message, self.translate("commands.hangman.no_game"))
                letter = rest_lower
                if letter in session["guessed"]:
                    return await self.send_response(
                        message, self.translate("commands.hangman.already_guessed", status=self._status_line(session))
                    )
                session["guessed"].add(letter)
                word = session["word"]
                if all(c in session["guessed"] for c in word):
                    self._sessions.end(channel)
                    return await self.send_response(message, self.translate("commands.hangman.won", word=word))
                wrong_count = len([g for g in session["guessed"] if g not in word])
                if wrong_count >= _MAX_WRONG:
                    self._sessions.end(channel)
                    return await self.send_response(message, self.translate("commands.hangman.lost", word=word))
                return await self.send_response(message, self._status_line(session))

            if not rest_lower:
                if session is not None:
                    return await self.send_response(
                        message,
                        self.translate(
                            "commands.hangman.running", category=session["category"], status=self._status_line(session)
                        ),
                    )
                return await self.send_response(
                    message,
                    self.translate("commands.hangman.usage", categories=", ".join(HANGMAN_WORDS.keys())),
                )

            return await self.send_response(
                message, self.translate("commands.hangman.unknown_action")
            )
        except Exception as e:
            self.logger.error(f"Error executing hangman command: {e}")
            return await self.send_response(message, self.translate("commands.hangman.error", error=str(e)))
