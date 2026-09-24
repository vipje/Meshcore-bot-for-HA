#!/usr/bin/env python3
"""
'morse' command for the MeshCore Bot.
Encodes text to morse code, or decodes morse code back to text.
"""

from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand

# Standard ITU morse table. Letters/digits + common punctuation.
_TEXT_TO_MORSE = {
    "a": ".-", "b": "-...", "c": "-.-.", "d": "-..", "e": ".",
    "f": "..-.", "g": "--.", "h": "....", "i": "..", "j": ".---",
    "k": "-.-", "l": ".-..", "m": "--", "n": "-.", "o": "---",
    "p": ".--.", "q": "--.-", "r": ".-.", "s": "...", "t": "-",
    "u": "..-", "v": "...-", "w": ".--", "x": "-..-", "y": "-.--",
    "z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.",
    "!": "-.-.--", "/": "-..-.", "-": "-....-", "@": ".--.-.",
}
_MORSE_TO_TEXT = {v: k for k, v in _TEXT_TO_MORSE.items()}

# Characters that a pure-morse message can consist of (word separator is '/').
_MORSE_CHARSET = set(".- /")


class MorseCommand(BaseCommand):
    """Encodes text to morse, or decodes morse back to text (auto-detected)."""

    name = "morse"
    keywords = ["morse"]
    description = "Tekst <-> morsecode (usage: morse hallo wereld, of morse .... .- .-.. .-.. ---)"
    category = "general"

    short_description = "Tekst <-> morsecode"
    usage = "morse <tekst>"
    examples = ["morse sos", "morse .... .- .-.. .-.. ---"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.morse_enabled = self.get_config_value(
            "Morse_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.morse_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "Zet tekst om naar morsecode, of morsecode terug naar tekst (automatisch herkend)."

    @staticmethod
    def _encode(text: str) -> str:
        words = text.lower().split()
        encoded_words = []
        for word in words:
            letters = [_TEXT_TO_MORSE.get(ch) for ch in word]
            encoded_words.append(" ".join(letter for letter in letters if letter))
        return " / ".join(w for w in encoded_words if w)

    @staticmethod
    def _decode(morse_text: str) -> str:
        words = morse_text.strip().split("/")
        decoded_words = []
        for word in words:
            letters = word.strip().split()
            chars = [_MORSE_TO_TEXT.get(letter, "") for letter in letters]
            decoded_words.append("".join(chars))
        return " ".join(w for w in decoded_words if w)

    def _looks_like_morse(self, content: str) -> bool:
        stripped = content.strip()
        if not stripped:
            return False
        # Must be built only from morse-safe characters, and contain at least
        # one dot/dash (otherwise a bare "/" or spaces would "match" too).
        return set(stripped) <= _MORSE_CHARSET and any(c in ".-" for c in stripped)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip()
            if content.lower().startswith("morse"):
                content = content[len("morse"):].strip()

            if not content:
                return await self.send_response(
                    message, self.translate("commands.morse.usage")
                )

            if self._looks_like_morse(content):
                decoded = self._decode(content)
                if not decoded:
                    return await self.send_response(message, self.translate("commands.morse.decode_error"))
                response = self.translate("commands.morse.decoded", text=decoded)
            else:
                encoded = self._encode(content)
                if not encoded:
                    return await self.send_response(
                        message, self.translate("commands.morse.encode_error")
                    )
                response = self.translate("commands.morse.encoded", text=encoded)

            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing morse command: {e}")
            return await self.send_response(message, self.translate("commands.morse.error", error=str(e)))
