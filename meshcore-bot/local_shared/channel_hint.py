"""Channel hints: tell people where a command does work.

Two situations, both handled here for *every* command (no per-plugin code):

1. Hint channels (for example a busy public channel): the bot listens there (greeter,
   announcements) but runs no commands. When someone types just a command word, the bot answers
   once in a while with a pointer to the channels where commands work.

2. A command that has its own channel list ([Xxx_Command] channels = ...) is used in a
   channel that is not on that list: the bot says where it does work.

Which commands give a hint is a setting **per plugin** (the "Hint in the public channel" field on each
command card of the dashboard's Plugins page, `[Xxx_Command] hint = ...`):

    off    no hint for this command (the default)
    word   a hint when the command word is typed alone: help, Test?, !ping, @[bot] help
    args   also when arguments follow, as many as the command's usage shows ("wx amsterdam")

Out of the box ping, test and help are set to `word`; every other command is `off`. A sentence that
merely contains the word ("ik help wel even mee", "heb jij een test voor mij") never gets a hint.

Other bots: when several bots serve the same region they would all answer the same message. A name
is recognised as a bot when it contains a bot marker (default the robot emoji, as in "Name|🤖") or
the word "bot" (`bot_words`): "DX1ABC-BOT", "Echobot", "BE-XYZ-Town-Bot", "BotAmsterdam". The word
counts when no letter follows it, so "Botond", "Abbott" and "Robotnik" stay people. Upper or lower
case does not matter. In a hint channel our bot waits `yield_seconds` plus a random extra of up to
8 seconds and stays quiet if another bot spoke in that channel in the meantime (or recently before).

Both are rate limited (one hint per channel per `cooldown_seconds`, and one per person per
`user_cooldown_seconds`) so the bot never floods a channel.

Config (config.ini):

    [ChannelHint]
    enabled = true
    channels = Public                 ; channels that get hints and no commands
    where = #bot,#test                ; where commands work (shown in the hint)
    message = We helpen je heel graag verder in {channels} || Voor de bot ben je welkom in {channels}
    restricted_message = Dat commando werkt hier niet. We helpen je graag verder in: {channels}
    ignore_words = hello,hi,hey
    bot_markers = 🤖
    bot_words = bot              ; comma separated; empty = only use bot_markers
    yield_seconds = 15           ; 0 = do not wait for other bots
    cooldown_seconds = 120
    user_cooldown_seconds = 600
"""
from __future__ import annotations

import asyncio
import random
import re
import time
from typing import Any, Optional

DEFAULT_MESSAGE = ("We helpen je heel graag verder in {channels} || Voor commando's en tests ben je welkom in {channels} || "
                   "Hier reageer ik niet op commando's, in {channels} wel! || Tip: probeer het in {channels}, daar help ik je graag")
VARIANT_SEPARATOR = "||"   # several texts in one field: the bot picks one at random, not the same one twice in a row
DEFAULT_RESTRICTED = "Dat commando werkt hier niet. We helpen je graag verder in: {channels}"
MAX_ARGUMENT_WORDS = 3
DEFAULT_WORD_COMMANDS = {"ping", "test", "help"}
DEFAULT_BOT_WORDS = "bot"
MARKED_KEY = "bots.marked"     # bot_metadata keys of the lists the `botlist` command edits
NEVER_KEY = "bots.never"
LIST_TTL_SECONDS = 30
SETTINGS_TTL_SECONDS = 30
MAX_LIST_ENTRIES = 300
MAX_NAME_LENGTH = 40
YIELD_JITTER_SECONDS = 8
INDEX_TTL_SECONDS = 30   # picks up dashboard changes to a command's hint setting within 30 s
MAX_MESSAGE_WORDS = MAX_ARGUMENT_WORDS + 3


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def join_channels(channels: list) -> str:
    """#a | #a of #b | #a, #b of #c"""
    if len(channels) <= 1:
        return "".join(channels)
    return ", ".join(channels[:-1]) + " of " + channels[-1]


def _split(value: str) -> list:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _bot_word_patterns(words: list) -> list:
    """Patterns that find a bot word in a sender name.

    The word matches in any case when no letter follows it (DX1ABC-BOT, Echobot, Bot 2, bot_nl), and
    as a capitalised prefix of a CamelCase name (BotAmsterdam). A letter after it ("Botond",
    "Robotnik") or a lowercase letter right after a capital ("Abbott") is not a match.
    """
    patterns = []
    for word in words:
        word = word.strip()
        if not word:
            continue
        patterns.append(re.compile(re.escape(word) + r"(?![^\W\d_])", re.IGNORECASE))
        patterns.append(re.compile(r"(?<![^\W\d_])" + re.escape(word.capitalize()) + r"(?=[A-Z])"))
    return patterns


class ChannelHint:
    def __init__(self, bot: Any):
        self.bot = bot
        self._last_channel: dict = {}
        self._last_user: dict = {}
        self._bot_seen: dict = {}      # channel -> when another bot last spoke there
        self._marked: list = []        # names an admin marked as bot (botlist add)
        self._never: list = []         # names an admin marked as never a bot (botlist not)
        self._lists_at = -LIST_TTL_SECONDS - 1.0
        self._index: dict = {}
        self._index_at = 0.0
        self._mention_re = None
        self._tasks: set = set()
        self._last_variant: dict = {}  # (channel, restricted) -> the text variant sent there last
        self._load_settings()

    def _load_settings(self) -> None:
        """Read [ChannelHint] from the bot's current config (again every SETTINGS_TTL_SECONDS, so a
        change saved on the dashboard's Plugins page, which makes the bot reload its config, works
        without a restart)."""
        self._settings_at = time.monotonic()
        cfg = self.bot.config
        s = "ChannelHint"
        has = cfg.has_section(s)

        def get(key, fallback=""):
            return cfg.get(s, key, fallback=fallback) if has else fallback

        self.enabled = cfg.getboolean(s, "enabled", fallback=False) if has else False
        self.channels = {_norm(c) for c in _split(get("channels"))}
        self.where = _split(get("where"))
        self.message = get("message", DEFAULT_MESSAGE) or DEFAULT_MESSAGE
        self.restricted_message = get("restricted_message", DEFAULT_RESTRICTED) or DEFAULT_RESTRICTED
        self.ignore_words = {w.lower() for w in _split(get("ignore_words", "hello,hi,hey"))}
        self.bot_markers = [m for m in _split(get("bot_markers", "🤖")) if m]
        self._bot_word_res = _bot_word_patterns(_split(get("bot_words", DEFAULT_BOT_WORDS)))
        self.yield_seconds = int(get("yield_seconds", "15") or 0)
        self.cooldown = int(get("cooldown_seconds", "120") or 120)
        self.user_cooldown = int(get("user_cooldown_seconds", "600") or 600)
        # Commands typed by another bot in a channel are ignored (direct messages are never affected).
        self.ignore_bot_commands = cfg.getboolean(s, "ignore_bot_commands", fallback=True)

    def _refresh_settings(self) -> None:
        if time.monotonic() - self._settings_at > SETTINGS_TTL_SECONDS:
            try:
                self._load_settings()
            except Exception:  # noqa: BLE001 - keep the last good settings
                self._settings_at = time.monotonic()

    # ---- hand-made lists (admin command `botlist`), kept in the bot's database ----

    def _read_names(self, key: str) -> list:
        import json
        try:
            raw = self.bot.db_manager.get_metadata(key)
            data = json.loads(raw) if raw else []
            return [str(n) for n in data if str(n).strip()]
        except Exception:  # noqa: BLE001 - runs for every channel message, must never raise
            return []

    def _write_names(self, key: str, names: list) -> None:
        import json
        self.bot.db_manager.set_metadata(key, json.dumps(names, ensure_ascii=False))

    def _lists(self) -> tuple:
        """(marked bots, never bots), re-read at most every LIST_TTL_SECONDS."""
        now = time.monotonic()
        if now - self._lists_at > LIST_TTL_SECONDS:
            self._marked = self._read_names(MARKED_KEY)
            self._never = self._read_names(NEVER_KEY)
            self._lists_at = now
        return self._marked, self._never

    def manual_lists(self) -> tuple:
        self._lists_at = 0.0
        return list(self._lists()[0]), list(self._lists()[1])

    def set_manual(self, name: str, status: Optional[bool]) -> Optional[bool]:
        """status True = always a bot, False = never a bot, None = back to automatic.

        Returns what the name was before (True / False / None). Raises ValueError for a bad name
        or a full list."""
        name = " ".join((name or "").split())
        if not name or len(name) > MAX_NAME_LENGTH:
            raise ValueError("naam ontbreekt of is te lang")
        key = name.lower()
        self._lists_at = 0.0
        marked, never = self._lists()
        was = True if any(n.lower() == key for n in marked) else (False if any(n.lower() == key for n in never) else None)
        marked = [n for n in marked if n.lower() != key]
        never = [n for n in never if n.lower() != key]
        if status is True:
            marked.append(name)
        elif status is False:
            never.append(name)
        if len(marked) > MAX_LIST_ENTRIES or len(never) > MAX_LIST_ENTRIES:
            raise ValueError(f"lijst vol (max {MAX_LIST_ENTRIES})")
        self._write_names(MARKED_KEY, marked)
        self._write_names(NEVER_KEY, never)
        self._lists_at = 0.0
        return was

    def classify_auto(self, name: str) -> tuple:
        """(is a bot, reason) by the automatic rules only: robot emoji or the word bot in the name."""
        self._refresh_settings()
        name = (name or "").strip()
        if not name:
            return False, "geen naam"
        if any(marker in name for marker in self.bot_markers):
            return True, "robot-emoji in de naam"
        if any(pattern.search(name) for pattern in self._bot_word_res):
            return True, "woord bot in de naam"
        return False, "geen bot-kenmerk"

    def manual_state(self, name: str) -> Optional[bool]:
        """True = an admin marked the name as a bot, False = never a bot, None = not in the lists."""
        key = (name or "").strip().lower()
        marked, never = self._lists()
        if any(n.lower() == key for n in never):
            return False
        if any(n.lower() == key for n in marked):
            return True
        return None

    def classify(self, name: str) -> tuple:
        """(is a bot, reason) for a sender name. Hand-made lists win over the automatic rules."""
        name = (name or "").strip()
        if not name:
            return False, "geen naam"
        state = self.manual_state(name)
        if state is False:
            return False, "handmatig: geen bot"
        if state is True:
            return True, "handmatig: bot"
        return self.classify_auto(name)

    def is_other_bot(self, message: Any) -> bool:
        sender = (getattr(message, "sender_id", "") or "")
        own = self.bot.config.get("Bot", "bot_name", fallback="")
        if not sender or sender.strip().lower() == own.strip().lower():
            return False
        return self.classify(sender)[0]

    def note_message(self, message: Any) -> None:
        """Remember that another bot spoke in this channel (called for every channel message)."""
        if getattr(message, "channel", None) and not getattr(message, "is_dm", False) and self.is_other_bot(message):
            self._bot_seen[_norm(message.channel)] = time.time()

    def is_hint_channel(self, message: Any) -> bool:
        self._refresh_settings()
        return bool(self.enabled and getattr(message, "channel", None) and _norm(message.channel) in self.channels)

    @staticmethod
    def _argument_spec(command: Any, keyword: str) -> tuple:
        """(max argument words, argument must be a command name) as far as usage/examples tell."""
        usage = str(getattr(command, "usage", "") or "").split()
        args = usage[1:]
        for i, token in enumerate(usage):          # usage may start with a label such as "Usage:"
            if token.strip("!/").lower() == keyword:
                args = usage[i + 1:]
                break
        slots = len(args)
        if slots == 0:
            slots = max((len(str(e).split()) - 1 for e in (getattr(command, "examples", None) or [])), default=0)
        max_words = min(slots + 1, MAX_ARGUMENT_WORDS) if slots > 0 else 0   # +1: a place name may be two words
        must_be_command = any("command" in a.lower() for a in args)
        return max_words, must_be_command

    def command_hint_mode(self, command: Any) -> str:
        """'off', 'word' or 'args' for one command, from its own [Xxx_Command] hint setting."""
        name = str(getattr(command, "name", "") or "").lower()
        try:
            section = command._derive_config_section_name()
        except Exception:  # noqa: BLE001
            section = f"{name.title()}_Command"
        value = self.bot.config.get(section, "hint", fallback=None) if self.bot.config.has_section(section) else None
        if value is None:
            return "word" if name in DEFAULT_WORD_COMMANDS else "off"
        value = value.strip().lower()
        if value in ("args", "arguments", "word+args", "with_arguments"):
            return "args"
        if value in ("", "off", "false", "no", "0", "none"):
            return "off"
        return "word"

    def _keyword_index(self) -> dict:
        """keyword -> (mode, max argument words, argument must be a command name), only for commands with a hint.

        Built from every command's own setting, so it is cached for a short time instead of being
        rebuilt for every message.
        """
        now = time.time()
        if self._index_at and now - self._index_at < INDEX_TTL_SECONDS:
            return self._index
        index: dict = {}
        for command in self.bot.command_manager.commands.values():
            mode = self.command_hint_mode(command)
            if mode == "off":
                continue
            for keyword in getattr(command, "keywords", None) or []:
                keyword = str(keyword).strip().lower()
                if keyword and " " not in keyword and keyword not in self.ignore_words:
                    max_words, must = self._argument_spec(command, keyword)
                    index[keyword] = (mode, max_words, must)
        self._index, self._index_at = index, now
        return index

    def is_command_attempt(self, message: Any) -> bool:
        """Does the message start with the word of a command that gives hints, with nothing extra it does not take?"""
        content = getattr(message, "content", "") or ""
        # Cheapest checks first: most messages are ordinary conversation.
        if len(content) > 160 or content.count(" ") > MAX_MESSAGE_WORDS:
            return False
        if self._mention_re is None:
            bot_name = self.bot.config.get("Bot", "bot_name", fallback="")
            self._mention_re = re.compile(r"@\[" + re.escape(bot_name) + r"\]", re.IGNORECASE) if bot_name else False
        if self._mention_re and "@[" in content:
            content = self._mention_re.sub(" ", content)
        words = content.split()
        if not words:
            return False
        index = self._keyword_index()
        first = words[0].lstrip("!/").rstrip("!?.,;:").lower()
        spec = index.get(first)
        if spec is None:
            return False
        extra = len(words) - 1
        if extra == 0:
            return True
        mode, max_words, must_be_command = spec
        if mode != "args" or extra > max_words:
            return False
        if must_be_command:
            return extra == 1 and words[1].lstrip("!/").rstrip("!?.,;:").lower() in {
                k for c in self.bot.command_manager.commands.values() for k in (getattr(c, "keywords", None) or [])}
        return True

    # kept for the message handler patch
    def matches_command(self, message: Any) -> bool:
        return self.is_command_attempt(message)

    def _pick_variant(self, field: str, key: tuple) -> str:
        """One of the texts in a field ("text A || text B"), at random but never the one this channel got last time."""
        variants = [v.strip() for v in (field or "").split(VARIANT_SEPARATOR) if v.strip()] or [field or ""]
        choices = [v for v in variants if v != self._last_variant.get(key)] or variants
        text = random.choice(choices)
        self._last_variant[key] = text
        return text

    async def send_hint(self, message: Any, where: Optional[list] = None, yield_to_bots: bool = False) -> bool:
        """Send a hint unless one went out recently. `where` = channels where the command works.

        With yield_to_bots the hint is sent in the background after a short wait, and dropped if
        another bot has answered in the meantime.
        """
        if not self.enabled:
            return False
        now = time.time()
        channel = _norm(message.channel)
        user = _norm(getattr(message, "sender_id", ""))
        if now - self._last_channel.get(channel, 0.0) < self.cooldown:
            return False
        if now - self._last_user.get((channel, user), 0.0) < self.user_cooldown:
            return False
        restricted = where is not None
        targets = list(where) if restricted else list(self.where)
        # Never point people back at the channel they are in.
        targets = [t for t in targets if _norm(t) != channel]
        text = self._pick_variant(self.restricted_message if restricted else self.message, (channel, restricted))
        if targets:
            text = text.replace("{channels}", join_channels(targets))
        elif restricted:
            text = "Dat commando werkt hier niet (alleen via DM)."
        else:
            text = text.replace("{channels}", "een van de commando-kanalen")

        if yield_to_bots and self.yield_seconds > 0:
            if now - self._bot_seen.get(channel, 0.0) < self.cooldown:
                return False   # another bot is already active here: no need
            self._last_channel[channel] = now
            self._last_user[(channel, user)] = now
            task = asyncio.ensure_future(self._send_after_yield(message.channel, channel, text, now))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return True
        self._last_channel[channel] = now
        self._last_user[(channel, user)] = now
        return await self._send_now(message.channel, text)

    async def _send_after_yield(self, channel_name: str, channel: str, text: str, trigger_time: float) -> bool:
        await asyncio.sleep(self.yield_seconds + random.uniform(0, YIELD_JITTER_SECONDS))
        if self._bot_seen.get(channel, 0.0) >= trigger_time - 2:
            self.bot.logger.info("ChannelHint: een andere bot heeft al gereageerd in %s, geen doorverwijzing", channel_name)
            return False
        return await self._send_now(channel_name, text)

    async def _send_now(self, channel_name: str, text: str) -> bool:
        try:
            return bool(await self.bot.command_manager.send_channel_message(
                channel_name, text, skip_user_rate_limit=True))
        except Exception as e:  # noqa: BLE001
            self.bot.logger.warning("ChannelHint: hint versturen mislukt: %s", e)
            return False


def get_channel_hint(bot: Any) -> ChannelHint:
    """One shared instance per bot, created on first use."""
    hint = getattr(bot, "_channel_hint", None)
    if hint is None:
        hint = ChannelHint(bot)
        bot._channel_hint = hint
    return hint
