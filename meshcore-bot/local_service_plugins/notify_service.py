"""Notification service plugin: tells you about things going wrong with the bot.

Watches the bot's own log and reports the interesting things to a destination on
the mesh: a room server, a (private) channel or a direct message. Radio problems
are also sent to Home Assistant (persistent notification and, optionally, a
notify service such as your phone), because when the radio is down the mesh is
of no use for telling you so.

Everything is batched and de-duplicated, because airtime is scarce:
  - the same message is sent at most once per `cooldown_minutes` (a count of the
    suppressed repeats is added next time),
  - messages that come in within `digest_seconds` of each other share one message,
  - a message is at most ~140 bytes and at most 3 messages go out per batch.

The service never reports on its own failures (they only go to the normal log),
so a broken destination cannot cause a loop. Passwords, tokens and long keys are
masked, and the text of other people's messages is never included.

Config (config.ini):

    [Notifications]
    enabled = true
    destination = room          # room | channel | dm
    target =                    # room: empty = the room the bot logs in to; channel: name; dm: public key
    min_level = ERROR           # ERROR | WARNING (for events not listed below)
    events = startup,radio,room_login,send_failed,contacts_full,ha_bridge,command_error,admin_command,error
    cooldown_minutes = 30
    digest_seconds = 60
    daily_summary = true
    summary_time = 08:00
    ha_notify = true
    ha_notify_service =         # e.g. notify.mobile_app_myphone (empty = only a persistent notification)
"""
from __future__ import annotations

import asyncio
import collections
import datetime
import logging
import os
import re
import time
from typing import Any, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

from .base_service import BaseServicePlugin

MAX_BYTES = 140
MAX_MESSAGES_PER_BATCH = 3
OWN_PREFIX = "Notify:"

# category -> (regex on the log message, cooldown seconds or None for cooldown_minutes)
PATTERNS = [
    ("radio", re.compile(
        r"radio is in zombie state|radio is offline|Reconnect failed|Could not reconnect|"
        r"Radio disconnect timed out", re.I), 600),
    ("room_login", re.compile(r"RoomServer_Login: .*(mislukt|fout|geen actieve)", re.I), None),
    ("send_failed", re.compile(r"^.{0,3}(DM|Channel message|Message)[^\n]{0,80}?\bfailed\b", re.I), None),
    ("contacts_full", re.compile(r"Contact list (at|near)", re.I), 86400),
    ("ha_bridge", re.compile(r"HomeAssistantBridge: webhook (post mislukt|antwoordde)", re.I), None),
    ("command_error", re.compile(r"Error executing (?:queued )?command '([^']+)'", re.I), None),
    # HARepeater warns at most once per repeater per day itself; the cooldown here is the same safety net.
    ("repeater", re.compile(r"HARepeater: (batterij laag|herstart|offline|ruisvloer hoog|airtime hoog|buur weg)", re.I), 86400),
]
ALL_EVENTS = ["startup", "radio", "room_login", "send_failed", "contacts_full",
              "ha_bridge", "command_error", "admin_command", "repeater", "error"]
INFO_CATEGORIES = {"startup", "radio_ok", "summary", "admin_command"}

_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_SECRET = re.compile(r"(?i)(bearer\s+|password\s*[=:]\s*|token\s*[=:]\s*|secret\s*[=:]\s*)\S+")
_URL_CRED = re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")


def sanitize(text: str) -> str:
    text = _SECRET.sub(lambda m: m.group(1) + "***", text)
    text = _URL_CRED.sub(r"\1***@", text)
    text = _HEX.sub(lambda m: m.group(0)[:8] + "…", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(text: str) -> str:
    return re.sub(r"\d+", "N", text.lower())[:120]


def fit(text: str, limit: int = MAX_BYTES) -> str:
    """Truncate to at most `limit` UTF-8 bytes, ending in an ellipsis if cut."""
    if len(text.encode("utf-8")) <= limit:
        return text
    while text and len((text + "…").encode("utf-8")) > limit:
        text = text[:-1]
    return text + "…"


def build_messages(alerts: list, infos: list, limit: int = MAX_BYTES,
                   max_messages: int = MAX_MESSAGES_PER_BATCH) -> list:
    """Pack alert and info lines into as few messages as possible (each <= limit bytes)."""
    messages: list = []
    for symbol, lines in (("⚠ ", alerts), ("ℹ ", infos)):
        current = ""
        for line in lines:
            line = fit(line, limit - len(symbol.encode("utf-8")))
            candidate = (current + " | " + line) if current else (symbol + line)
            if len(candidate.encode("utf-8")) <= limit:
                current = candidate
            else:
                if current:
                    messages.append(current)
                current = symbol + line
        if current:
            messages.append(current)
    if len(messages) > max_messages:
        dropped = len(messages) - max_messages
        messages = messages[:max_messages]
        messages[-1] = fit(messages[-1], limit - 12) + f" (+{dropped} meer)"
        messages[-1] = fit(messages[-1], limit)
    return messages


# INFO lines the service needs (everything else at INFO, such as the many routing lines, is skipped
# before any work is done). Warnings and errors always pass.
_INTERESTING_INFO = ("Admin access granted", "Command '", "Processing message: ", "Connected to:")


class _LogHandler(logging.Handler):
    def __init__(self, service: "NotifyService"):
        super().__init__(level=logging.INFO)
        self.service = service

    def emit(self, record: logging.LogRecord) -> None:
        try:
            svc = self.service
            if svc._sending:            # never react to our own sending
                return
            if record.levelno < logging.WARNING:
                raw = record.msg if isinstance(record.msg, str) else ""
                if not raw.startswith(_INTERESTING_INFO):
                    return
            msg = record.getMessage()
            if msg.startswith(OWN_PREFIX):
                return
            loop = svc._loop
            if loop is None or loop.is_closed():
                return
            loop.call_soon_threadsafe(svc._ingest, record.levelno, msg, time.time())
        except Exception:  # noqa: BLE001 - a log handler must never raise
            pass


class NotifyService(BaseServicePlugin):
    config_section = "Notifications"

    # Settings card on the dashboard's Plugins page (the add-on options for this moved here in 2.7.0).
    settings_schema = [
        {"key": "destination", "label": "Send notifications to", "type": "enum", "default": "room",
         "options": [{"value": "room", "label": "The room server (log room)"},
                     {"value": "channel", "label": "A channel"},
                     {"value": "dm", "label": "A direct message"}],
         "help": "Where the bot reports problems and the daily summary."},
        {"key": "target", "label": "Room key, channel or contact", "type": "str", "default": "",
         "help": ("Empty with 'room' uses the room server login key. For a channel: the channel name. "
                  "For a direct message: the contact's public key.")},
        {"key": "min_level", "label": "Report from level", "type": "enum", "default": "ERROR",
         "options": [{"value": "ERROR", "label": "Errors only"}, {"value": "WARNING", "label": "Warnings and errors"}],
         "help": "Which log lines count as a problem."},
        {"key": "events", "label": "Events to report", "type": "list",
         "default": ['startup', 'radio', 'room_login', 'send_failed', 'contacts_full', 'ha_bridge', 'command_error', 'admin_command', 'repeater', 'error'],
         "pattern": "(startup|radio|room_login|send_failed|contacts_full|ha_bridge|command_error|admin_command|repeater|error)",
         "help": ("Comma-separated. Choose from: startup, radio, room_login, send_failed, contacts_full, ha_bridge, "
                  "command_error, admin_command, repeater, error. (repeater = the warnings of the HARepeater card: "
                  "low battery, restart, offline, noise, airtime.)")},
        {"key": "cooldown_minutes", "label": "Same message again after", "type": "int", "default": 30,
         "min": 0, "max": 1440, "unit": "min",
         "help": "The same problem is reported at most once per this time (0 = every time)."},
        {"key": "digest_seconds", "label": "Collect messages for", "type": "int", "default": 60,
         "min": 5, "max": 3600, "unit": "s",
         "help": "Problems that come close together are sent as one message to spare airtime."},
        {"key": "daily_summary", "label": "Daily summary", "type": "bool", "default": True,
         "help": "One message a day with uptime, radio state, contacts and counters."},
        {"key": "summary_time", "label": "Time of the daily summary", "type": "str", "default": "08:00",
         "pattern": "([01][0-9]|2[0-3]):[0-5][0-9]", "help": "24-hour time, HH:MM."},
        {"key": "ha_notify", "label": "Also tell Home Assistant about radio problems", "type": "bool", "default": True,
         "help": "Works when the mesh does not: a persistent notification in Home Assistant."},
        {"key": "ha_notify_service", "label": "Home Assistant notify service", "type": "str", "default": "",
         "help": "Optional, for a push message to your phone, for example notify.mobile_app_myphone."},
    ]
    description = "Reports failures and other things you want to know about to a room server, channel or DM"

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        s = self.config_section
        has = cfg.has_section(s)

        def get(key, fallback=""):
            return cfg.get(s, key, fallback=fallback) if has else fallback

        self.notify_enabled = cfg.getboolean(s, "enabled", fallback=False) if has else False
        self.destination = get("destination", "room").strip().lower()
        self.target = get("target").strip()
        self.min_level = logging.WARNING if get("min_level", "ERROR").strip().upper() == "WARNING" else logging.ERROR
        events = [e.strip() for e in get("events", ",".join(ALL_EVENTS)).split(",") if e.strip()]
        self.events = set(events)
        self.cooldown = max(0, int(get("cooldown_minutes", "30") or 30)) * 60
        self.digest_seconds = max(1, int(get("digest_seconds", "60") or 60))
        self.daily_summary = cfg.getboolean(s, "daily_summary", fallback=True) if has else True
        self.summary_time = get("summary_time", "08:00").strip() or "08:00"
        self.ha_notify = cfg.getboolean(s, "ha_notify", fallback=True) if has else True
        self.ha_notify_service = get("ha_notify_service").strip()
        self.version = os.environ.get("ADDON_VERSION", "").strip()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: "asyncio.Queue" = asyncio.Queue()
        self._handler: Optional[_LogHandler] = None
        self._tasks: list = []
        self._background: set = set()
        self._session = None
        self._sending = False
        self._radio_problem = False
        self._limit_refreshed = 0.0
        self._last_sent: dict = {}
        self._suppressed: dict = collections.defaultdict(int)
        self._last_admin: tuple = (0.0, "")
        self._last_origin: tuple = (0.0, "", "")   # (time, sender name, "DM" or channel) of the message being processed
        self.started_at = time.time()
        # Counters for the daily summary (reset after it is sent) and for `status`.
        self.counters = {"commands": 0, "errors": 0, "warnings": 0}
        self.issues: collections.deque = collections.deque(maxlen=20)

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if not self.notify_enabled:
            self.logger.debug("Notify: uitgeschakeld")
            self.enabled = True   # stays loaded: the `status` command uses it
            self._install_handler_for_status()
            return
        if self.destination not in ("room", "channel", "dm"):
            self.logger.warning("Notify: onbekende bestemming %r, meldingen uit", self.destination)
            self.enabled = True
            return
        self._loop = asyncio.get_running_loop()
        self._running = True
        if aiohttp is not None:
            self._session = aiohttp.ClientSession()
        self._install_handler()
        self._tasks = [asyncio.create_task(self._digest_loop())]
        if "startup" in self.events:
            self._tasks.append(asyncio.create_task(self._startup_message()))
        if self.daily_summary:
            self._tasks.append(asyncio.create_task(self._summary_loop()))

    def _install_handler(self) -> None:
        self._handler = _LogHandler(self)
        logging.getLogger("MeshCoreBot").addHandler(self._handler)

    def _install_handler_for_status(self) -> None:
        """Counters and the issue list for `status` also work with notifications off."""
        self._loop = asyncio.get_running_loop()
        self._install_handler()

    async def stop(self) -> None:
        self._running = False
        if self._handler is not None:
            logging.getLogger("MeshCoreBot").removeHandler(self._handler)
            self._handler = None
        for task in list(self._tasks) + list(self._background):
            task.cancel()
        self._tasks = []
        if self._session is not None:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------ ingest
    def _classify(self, level: int, msg: str, ts: float):
        """Return (category, text) for a log line, or None to ignore it."""
        for category, pattern, _cooldown in PATTERNS:
            m = pattern.search(msg)
            if not m:
                continue
            if category == "command_error":
                return category, f"Commando '{m.group(1)}' crasht"
            if category == "contacts_full":
                pct = re.search(r"(\d+(?:\.\d+)?)\s*%", msg)
                return category, f"Contactlijst vol{f' ({pct.group(1)}%)' if pct else ''}"
            if category == "room_login":
                return category, "Inloggen op de room mislukt"
            if category == "ha_bridge":
                return category, "Koppeling met Home Assistant faalt"
            if category == "repeater":
                return category, sanitize(msg.split("HARepeater: ", 1)[-1])
            return category, sanitize(msg.lstrip("❌ ").strip())
        m = re.match(r"^Processing message: '.*' from (.+) in (\S+)$", msg)
        if m:
            self._last_origin = (ts, m.group(1), m.group(2))
            return None
        m = re.search(r"Admin access granted for (.+?) \(pubkey", msg)
        if m:
            self._last_admin = (ts, m.group(1))
            return None
        m = re.search(r"Command '(\w+)' matched, executing", msg)
        if m:
            self.counters["commands"] += 1
            when, who = self._last_admin
            if who and ts - when < 1.5:
                self._last_admin = (0.0, "")
                o_ts, o_sender, o_where = self._last_origin
                if ts - o_ts < 3 and self._is_destination(o_sender, o_where):
                    return None   # typed in the notification destination itself: you see it there already
                known = ts - o_ts < 3 and o_where
                place = f" ({o_where})" if known else ""
                return "admin_command", f"Admin {who}{place}: {m.group(1)}"
            return None
        if self._radio_problem and msg.startswith("Connected to:"):
            return "radio_ok", "Radio weer verbonden"
        if level >= self.min_level:
            return "error", sanitize(msg)
        return None

    def _contact_name(self, key: str) -> str:
        contacts = getattr(getattr(self.bot, "meshcore", None), "contacts", None) or {}
        contact = contacts.get(key)
        if contact is None:
            for k, c in contacts.items():
                if (c.get("public_key") or k or "").lower().startswith(key.lower()[:12]):
                    contact = c
                    break
        if not contact:
            return ""
        return (contact.get("adv_name") or contact.get("name") or "").strip().lower()

    def _is_destination(self, sender: str, where: str) -> bool:
        """Did this message come from the place the notifications go to?"""
        if self.destination == "channel":
            return where != "DM" and where.lstrip("#").lower() == self.target.lstrip("#").lower()
        if where != "DM":
            return False
        name = self._contact_name(self._destination_key())
        return bool(name) and sender.strip().lower() == name

    def _ingest(self, level: int, msg: str, ts: float) -> None:
        if level >= logging.ERROR:
            self.counters["errors"] += 1
        elif level >= logging.WARNING:
            self.counters["warnings"] += 1
        classified = self._classify(level, msg, ts)
        if classified is None:
            return
        category, text = classified
        if category == "radio":
            self._radio_problem = True
        elif category == "radio_ok":
            self._radio_problem = False
        if level >= logging.WARNING or category in ("radio", "radio_ok", "send_failed"):
            self.issues.append((ts, category, text))
        wanted = category in self.events or (category == "radio_ok" and "radio" in self.events)
        if category == "repeater" and not wanted:
            # The service only writes the warnings that are switched on on its own card (Plugins -> HARepeater), so they
            # also work for an events list that was saved before this event existed.
            wanted = self.bot.config.getboolean("HARepeater", "enabled", fallback=False)
        if not wanted or not self.notify_enabled:
            return
        if category in ("radio", "radio_ok"):
            self._spawn(self._ha_notify(category, text))
        cooldown = self.cooldown
        for name, _pattern, special in PATTERNS:
            if name == category and special is not None:
                cooldown = special
        if category == "admin_command":
            cooldown = 60
        key = category + ":" + normalize_key(text)
        last = self._last_sent.get(key, 0.0)
        if ts - last < cooldown:
            self._suppressed[key] += 1
            return
        self._last_sent[key] = ts
        repeats = self._suppressed.pop(key, 0)
        if repeats:
            text = f"{text} (+{repeats}x eerder)"
        self._queue.put_nowait((category, text))

    def _spawn(self, coro) -> None:
        if self._loop is not None:
            task = self._loop.create_task(coro)
            self._background.add(task)
            task.add_done_callback(self._background.discard)

    # ------------------------------------------------------------------ sending
    async def _digest_loop(self) -> None:
        while self._running:
            first = await self._queue.get()
            await asyncio.sleep(self.digest_seconds)
            batch = [first]
            while not self._queue.empty():
                batch.append(self._queue.get_nowait())
            await self._send_batch(batch)

    async def _send_batch(self, batch: list) -> None:
        alerts = [text for cat, text in batch if cat not in INFO_CATEGORIES]
        infos = [text for cat, text in batch if cat in INFO_CATEGORIES]
        for message in build_messages(alerts, infos):
            await self._send(message)

    def _destination_key(self) -> str:
        if self.destination == "room":
            return self.target or self.bot.config.get("RoomServer_Login", "public_key", fallback="").strip()
        return self.target

    async def _send(self, text: str) -> bool:
        key = self._destination_key()
        if not key:
            self.logger.warning("%s geen bestemming ingesteld voor meldingen", OWN_PREFIX)
            return False
        cm = getattr(self.bot, "command_manager", None)
        if cm is None or not getattr(self.bot, "connected", False):
            self.logger.info("%s niet verzonden (radio niet verbonden): %s", OWN_PREFIX, text)
            return False
        # Een melding is geen antwoord aan een gebruiker: de bot noteert elke geslaagde
        # verzending in de gedeelde zendbegrenzing (rate_limit_seconds, standaard 10 s),
        # ook als de controle is overgeslagen. Zonder dit herstel wordt een commando dat
        # kort na een melding binnenkomt geweigerd ("Rate limited. Wait 6.0 seconds").
        limiter = getattr(self.bot, "rate_limiter", None)
        last_send_before = getattr(limiter, "last_send", None)
        self._sending = True
        try:
            if self.destination == "channel":
                ok = await cm.send_channel_message(key, text, skip_user_rate_limit=True)
            else:
                ok = await cm.send_dm(key, text, skip_user_rate_limit=True)
        except Exception as e:  # noqa: BLE001
            ok = False
            self.logger.info("%s verzenden mislukt: %s", OWN_PREFIX, e)
        finally:
            self._sending = False
            if last_send_before is not None:
                try:
                    with limiter._lock:
                        limiter.last_send = last_send_before
                except Exception:  # noqa: BLE001
                    pass
        if not ok:
            self.logger.info("%s verzenden mislukt: %s", OWN_PREFIX, text)
        return bool(ok)

    async def _ha_notify(self, category: str, text: str) -> None:
        """Home Assistant path for radio problems (works when the mesh does not)."""
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not (self.ha_notify and token and self._session is not None):
            return
        bot_name = self.bot.config.get("Bot", "bot_name", fallback="MeshCore Bot")
        headers = {"Authorization": f"Bearer {token}"}
        base = "http://supervisor/core/api/services"
        calls = [(f"{base}/persistent_notification/create",
                  {"title": bot_name, "message": text, "notification_id": "meshcore_bot_radio"})]
        if self.ha_notify_service and "." in self.ha_notify_service:
            domain, service = self.ha_notify_service.split(".", 1)
            calls.append((f"{base}/{domain}/{service}", {"title": bot_name, "message": text}))
        for url, body in calls:
            try:
                async with self._session.post(url, json=body, headers=headers,
                                              timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status >= 300:
                        self.logger.info("%s HA-melding gaf status %s", OWN_PREFIX, resp.status)
            except Exception as e:  # noqa: BLE001
                self.logger.info("%s HA-melding mislukt: %s", OWN_PREFIX, e)

    # ------------------------------------------------------------------ startup and summary
    async def refresh_contact_limit(self) -> None:
        """Ask the radio for its real contact limit (the bot starts with a default of 300)."""
        if time.time() - self._limit_refreshed < 300:
            return
        rm = getattr(self.bot, "repeater_manager", None)
        update = getattr(rm, "_update_contact_limit_from_device", None)
        if update is None:
            return
        self._limit_refreshed = time.time()
        try:
            await asyncio.wait_for(update(), timeout=20)
        except Exception as e:  # noqa: BLE001
            self.logger.info("%s kon contactlimiet niet ophalen: %s", OWN_PREFIX, e)

    def _contacts_line(self) -> str:
        contacts = getattr(getattr(self.bot, "meshcore", None), "contacts", None) or {}
        limit = getattr(getattr(self.bot, "repeater_manager", None), "contact_limit", 0)
        return f"contacten {len(contacts)}" + (f"/{limit}" if limit else "")

    def radio_state(self) -> str:
        if getattr(self.bot, "is_radio_zombie", False):
            return "zombie"
        if getattr(self.bot, "is_radio_offline", False) or not getattr(self.bot, "connected", True):
            return "offline"
        return "ok"

    async def _startup_message(self) -> None:
        await asyncio.sleep(45)   # let the connection and room login settle
        await self.refresh_contact_limit()
        version = f" v{self.version}" if self.version else ""
        self._queue.put_nowait(("startup", f"Bot gestart{version} · radio {self.radio_state()} · {self._contacts_line()}"))

    @staticmethod
    def seconds_until(hhmm: str, now: Optional[datetime.datetime] = None) -> float:
        now = now or datetime.datetime.now()
        try:
            hour, minute = [int(x) for x in hhmm.split(":")]
        except ValueError:
            hour, minute = 8, 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        return (target - now).total_seconds()

    def summary_text(self) -> str:
        c = self.counters
        return (f"Overzicht: up {format_duration(time.time() - self.started_at)} · {c['commands']} cmd · "
                f"{c['errors']} fouten · {c['warnings']} waarsch. · {self._contacts_line()} · radio {self.radio_state()}")

    async def _summary_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.seconds_until(self.summary_time))
            await self.refresh_contact_limit()
            self._queue.put_nowait(("summary", self.summary_text()))
            self.counters = {"commands": 0, "errors": 0, "warnings": 0}
            await asyncio.sleep(61)


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}u")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)
