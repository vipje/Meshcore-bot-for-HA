#!/usr/bin/env python3
"""
'info bot' command for the MeshCore Bot (direct message only).

Tells whoever asks what this bot is and what they need to run one of their own, in at most three short
messages. The GitHub link, the language (nl or en) and one extra line about yourself are settings on the
dashboard's Plugins page (card `info`), so nothing personal is hard-coded. Without a link the link part is
left out.
"""

from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand

MAX_BYTES = 130
MAX_MESSAGES = 3

TEXTS = {
    "nl": {
        "what": "Ik ben een MeshCore-bot: een add-on voor Home Assistant, gebouwd op meshcore-bot van agessaman. Typ help voor mijn commando's.",
        "need": "Zelf zo'n bot? Nodig: Home Assistant, een MeshCore-USB-radio (bv. Seeed XIAO ESP32S3) en de add-ons MeshCore Proxy + Bot.",
        "more": "Meer info en download: {url}",
    },
    "en": {
        "what": "I am a MeshCore bot: a Home Assistant add-on built on agessaman's meshcore-bot. Type help for my commands.",
        "need": "Want your own? You need Home Assistant, a MeshCore USB radio (e.g. Seeed XIAO ESP32S3) and the MeshCore Proxy + Bot add-ons.",
        "more": "More info and download: {url}",
    },
    "de": {
        "what": "Ich bin ein MeshCore-Bot: ein Home-Assistant-Add-on, aufgebaut auf meshcore-bot von agessaman. Tippe help für meine Befehle.",
        "need": "Selbst so einen Bot? Nötig: Home Assistant, ein MeshCore-USB-Funkgerät (z.B. Seeed XIAO ESP32S3) und die Add-ons MeshCore Proxy + Bot.",
        "more": "Mehr Infos und Download: {url}",
    },
    "fr": {
        "what": "Je suis un bot MeshCore : un add-on Home Assistant basé sur meshcore-bot d'agessaman. Tapez help pour mes commandes.",
        "need": "Envie du vôtre ? Il faut : Home Assistant, une radio USB MeshCore (par ex. Seeed XIAO ESP32S3) et les add-ons MeshCore Proxy + Bot.",
        "more": "Plus d'infos et téléchargement : {url}",
    },
}


def fit(text: str, limit: int = MAX_BYTES) -> str:
    if len(text.encode("utf-8")) <= limit:
        return text
    while text and len((text + "…").encode("utf-8")) > limit:
        text = text[:-1]
    return text + "…"


def build_messages(language: str = "nl", github_url: str = "", extra_line: str = "") -> list:
    """The reply as at most MAX_MESSAGES messages of at most MAX_BYTES bytes each."""
    text = TEXTS.get((language or "nl").strip().lower(), TEXTS["nl"])
    pieces = [text["what"], text["need"]]
    if (github_url or "").strip():
        pieces.append(text["more"].format(url=github_url.strip()))
    if (extra_line or "").strip():
        pieces.append(" ".join(extra_line.split()))
    messages: list = []
    for piece in pieces:
        piece = fit(piece)
        candidate = f"{messages[-1]} | {piece}" if messages else ""
        if messages and len(candidate.encode("utf-8")) <= MAX_BYTES:
            messages[-1] = candidate
        else:
            messages.append(piece)
    if len(messages) > MAX_MESSAGES:
        messages = messages[:MAX_MESSAGES]
    return messages


class InfoCommand(BaseCommand):
    """`info bot`: what this bot is and what you need for your own."""

    name = "info"
    keywords = ["info bot", "infobot"]
    description = "Wat deze bot is en wat je nodig hebt voor een eigen bot"
    category = "general"
    requires_dm = True

    short_description = "Over deze bot"
    usage = "info bot"
    examples = ["info bot"]

    settings_schema = [
        {"key": "github_url", "label": "GitHub link", "type": "str", "default": "",
         "help": "Shown at the end of the reply. Empty = no link (for example while the add-ons are not published yet)."},
        {"key": "language", "label": "Language of the reply", "type": "enum", "default": "nl",
         "options": [
             {"value": "nl", "label": "Nederlands"}, {"value": "en", "label": "English"},
             {"value": "de", "label": "Deutsch"}, {"value": "fr", "label": "Français"},
         ]},
        {"key": "extra_line", "label": "One extra line", "type": "str", "default": "",
         "help": "For example who runs this bot. Empty = nothing. Keep it short: a message holds about 130 bytes."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.info_enabled = self.get_config_value("Info_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.info_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "info bot vertelt wat deze bot is en wat je nodig hebt voor een eigen bot (alleen via DM)."

    async def execute(self, message: MeshMessage) -> bool:
        try:
            get = lambda key, default="": self.get_config_value("Info_Command", key, fallback=default)  # noqa: E731
            messages = build_messages(str(get("language", "nl")), str(get("github_url")), str(get("extra_line")))
            if len(messages) == 1:
                return await self.send_response(message, messages[0])
            return await self.send_response_chunked(message, messages)
        except Exception as e:
            self.logger.error(f"Error executing info command: {e}")
            return await self.send_response(message, self.translate("commands.info.error", error=str(e)))
