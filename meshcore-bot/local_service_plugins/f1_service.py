#!/usr/bin/env python3
"""Formula 1 in the #f1 channel (card: Plugins -> F1), with the prediction game.

Reads the F1 sensors of Home Assistant (`f1_sensor`, read-only, the add-on's own permission) and posts sparingly in
one channel: a countdown every day at noon, the race weekend with its times, a reminder before qualifying and the
race, the results and the standings after the race, and (if the live sensors work) the top five at 25/50/75% of the
race and a note for a safety car or red flag. What is posted when is decided by `f1_data.plan()`; this service reads,
sends and remembers what was posted, so a restart never repeats a message.

The `f1` command (f1_command.py) answers questions in the channel and by direct message and runs the game.
"""
import asyncio
import json
import os
import time
from typing import Any, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

from .base_service import BaseServicePlugin

try:
    from .. import f1_data as F
    from ..f1_game import F1Game
except ImportError:  # pragma: no cover - unit tests import the files directly
    import f1_data as F   # type: ignore[no-redef]
    from f1_game import F1Game   # type: ignore[no-redef]

STATES_URL = "http://supervisor/core/api/states"
STATE_KEY = "f1.state"
IDLE_READ_S = 300
SOON_READ_S = 60
MAX_POSTED_KEYS = 400
GAP_BETWEEN_MESSAGES_S = 6
SEND_BACKOFF_S = 900
ERROR_LOG_INTERVAL_S = 6 * 3600


class F1Service(BaseServicePlugin):
    config_section = "F1"
    name = "f1"
    description = "Formula 1 in a channel: countdown, race weekend, results, standings, live updates and a prediction game"

    settings_schema = [
        {"key": "channel", "label": "Channel for the F1 posts", "type": "str", "default": "#f1",
         "help": ("The channel name exactly as on your radio. Create it in the MeshCore app first (a hashtag channel). Do NOT add it to "
                  "*Bot, Channels to listen on*: the f1 command gets this channel from its own card instead, so only f1 works there.")},
        {"key": "timezone", "label": "Time zone for the texts", "type": "str", "default": "Europe/Amsterdam"},
        {"key": "language", "label": "Language of the posts", "type": "enum", "default": "nl",
         "options": [
             {"value": "nl", "label": "Nederlands"}, {"value": "en", "label": "English"},
             {"value": "de", "label": "Deutsch"}, {"value": "fr", "label": "Français"},
         ],
         "help": ("These posts have no sender to detect a language from (unlike the f1 command, which answers in "
                  "whoever asked their own language), so this fixes the language for the channel.")},
        {"key": "post_daily", "label": "Countdown every day", "type": "bool", "default": True,
         "help": "One message a day (until 3 days before the race), then the announcement of the race weekend with all times."},
        {"key": "daily_time", "label": "Time of the daily message", "type": "str", "default": "12:00",
         "pattern": "([01][0-9]|2[0-3]):[0-5][0-9]", "help": "24-hour time, HH:MM."},
        {"key": "reminder_minutes", "label": "Reminder before qualifying, sprint and race", "type": "int", "default": 60,
         "min": 0, "max": 240, "unit": "min", "help": "0 = no reminders."},
        {"key": "post_results", "label": "Post results and standings", "type": "bool", "default": True,
         "help": "After the race (and the sprint): top 10, the winner, the championship top 5 and the constructors' top 3."},
        {"key": "post_live", "label": "Live updates during a session", "type": "bool", "default": True,
         "help": ("Top five at the chosen points of the race, safety car and red flag, and the qualifying result. Needs the live sensors of "
                  "f1_sensor; when they are unavailable nothing is posted.")},
        {"key": "live_milestones", "label": "Race update at % of the laps", "type": "list", "default": [25, 50, 75],
         "pattern": "[0-9]{1,2}", "help": "Comma-separated percentages. Plus the start, and the result afterwards."},
        {"key": "max_live_posts", "label": "At most this many live posts per race", "type": "int", "default": 8,
         "min": 1, "max": 30, "help": "A safety net for the airtime."},
        {"key": "live_read_seconds", "label": "Read Home Assistant every (during a session)", "type": "int", "default": 30,
         "min": 15, "max": 300, "unit": "s", "help": "Reading costs no airtime. Outside sessions it reads every 5 minutes."},
        {"key": "game_enabled", "label": "Prediction game", "type": "bool", "default": True,
         "help": "f1 voorspel <code> by direct message; points after the race; f1 spel shows the standings."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        s = self.config_section
        has = cfg.has_section(s)

        def get(key, fallback=""):
            return cfg.get(s, key, fallback=fallback) if has else fallback

        def getbool(key, fallback):
            return cfg.getboolean(s, key, fallback=fallback) if has else fallback

        def getint(key, fallback):
            try:
                return int(get(key, str(fallback)) or fallback)
            except ValueError:
                return fallback

        milestones = []
        for item in get("live_milestones", "25, 50, 75").split(","):
            if item.strip().isdigit() and 0 < int(item) < 100:
                milestones.append(int(item))
        self.channel = (get("channel", "#f1") or "#f1").strip()
        if self.channel.startswith("#"):
            self.channel = self.channel.lower()   # a hashtag channel's key comes from its lowercase name
        self.cfg = {
            "timezone": get("timezone", "Europe/Amsterdam").strip() or "Europe/Amsterdam",
            "daily_time": get("daily_time", "12:00").strip() or "12:00",
            "post_daily": getbool("post_daily", True), "reminder_minutes": getint("reminder_minutes", 60),
            "post_results": getbool("post_results", True), "post_live": getbool("post_live", True),
            "live_milestones": milestones or [25, 50, 75], "max_live_posts": getint("max_live_posts", 8),
        }
        self.live_read = max(15, getint("live_read_seconds", 30))
        self.game_enabled = getbool("game_enabled", True)
        self.tz = F.get_tz(self.cfg["timezone"])
        language = (get("language", "nl") or "nl").strip().lower()
        get_translator = getattr(bot, "get_translator", None)
        self.translate = get_translator(language).translate if get_translator else bot.translator.translate

        self.snapshot: dict = F.parse([])
        self.last_read = 0.0
        self.last_error = ""
        self.st: dict = {"posted": []}
        self.game: Optional[F1Game] = None
        self._task: Optional[asyncio.Task] = None
        self._session = None
        self._error_logged: dict = {}
        self._send_blocked_until = 0.0
        self._first_report = False

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if aiohttp is None:
            self.logger.warning("F1: aiohttp ontbreekt, service niet gestart")
            return
        self._running = True
        self._load_state()
        try:
            self.game = F1Game(self.bot.db_manager)
            self.game.ensure_tables()
        except Exception as e:  # noqa: BLE001
            self.game = None
            self.logger.warning("F1: spel-tabellen maken mislukt: %s", e)
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
        self._task = asyncio.get_running_loop().create_task(self._loop())
        self.logger.info("F1: gestart (kanaal %s, elke %d s tijdens een sessie, anders elke 5 min)", self.channel, self.live_read)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _loop(self) -> None:
        await asyncio.sleep(20)
        while self._running:
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - one bad reading must not stop the loop
                self._complain("loop", f"F1: ronde mislukt: {e}")
            await asyncio.sleep(self._delay())

    def _delay(self) -> int:
        live = self.snapshot.get("live") or {}
        if live.get("status") in ("live", "suspended", "break", "pre"):
            return self.live_read
        nxt = self.snapshot.get("next")
        if nxt:
            now = time.time()
            if any(-3 * 3600 < ts - now < 90 * 60 for ts in nxt["sessions"].values()):
                return SOON_READ_S
        return IDLE_READ_S

    # ------------------------------------------------------------------ reading
    def _complain(self, kind: str, text: str) -> None:
        self.last_error = text
        now = time.time()
        if now - self._error_logged.get(kind, 0.0) >= ERROR_LOG_INTERVAL_S:
            self._error_logged[kind] = now
            self.logger.warning(text)

    async def _fetch(self) -> Optional[list]:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        try:
            async with self._session.get(STATES_URL, headers={"Authorization": f"Bearer {token}"}) as resp:
                if resp.status in (401, 403):
                    self._complain("auth", f"F1: geen toegang tot de Home Assistant-API (HTTP {resp.status})")
                    return None
                if resp.status != 200:
                    self._complain("http", f"F1: Home Assistant antwoordde HTTP {resp.status}")
                    return None
                return await resp.json(content_type=None)
        except asyncio.TimeoutError:
            self._complain("timeout", "F1: Home Assistant antwoordt niet (time-out)")
        except Exception as e:  # noqa: BLE001
            self._complain("net", f"F1: Home Assistant niet bereikbaar: {e}")
        return None

    async def refresh(self, now_ts: Optional[float] = None) -> bool:
        states = await self._fetch()
        if states is None:
            return False
        return await self.process(states, now_ts if now_ts is not None else time.time())

    async def process(self, states: list, now_ts: float) -> bool:
        """One round: read the snapshot, decide, post. Split from refresh() so it can be tested with a fake clock."""
        self.snapshot = F.parse(states)
        self.last_read = now_ts
        self.last_error = ""
        self._report_once()
        actions, upd = F.plan(self.snapshot, self.st, now_ts, {**self.cfg, "game": self.game_enabled}, self.translate)
        self.st.update(upd)
        for action in actions:
            ok = await self._post(action["messages"], now_ts)
            if ok:
                self._mark(action["key"])
                if action["kind"] == "live":
                    self.st["last_live_ts"] = now_ts
                if action["kind"] == "result":
                    await self._after_race(action, now_ts)
        self._save_state()
        return True

    def _report_once(self) -> None:
        """One log line the first time: what was found, so a missing sensor is visible."""
        if self._first_report:
            return
        self._first_report = True
        nxt, last, live = self.snapshot["next"], self.snapshot["last_race"], self.snapshot["live"]
        self.logger.info(
            "F1: gevonden: volgende race %s | laatste uitslag ronde %s | klassement %d rijders, %d teams | live: sessie=%s status=%s ronde=%s posities=%d",
            f"{nxt['race_name']} (ronde {nxt['round']})" if nxt else "geen", last["round"] if last else "geen",
            len(self.snapshot["drivers"]), len(self.snapshot["teams"]), live.get("session"), live.get("status"), live.get("lap"), len(live.get("positions", [])))

    # ------------------------------------------------------------------ posting
    async def _post(self, messages: list, now_ts: float) -> bool:
        if now_ts < self._send_blocked_until:
            return False
        for i, text in enumerate(messages):
            if i:
                await asyncio.sleep(GAP_BETWEEN_MESSAGES_S)
            if not await self._send(text):
                self._send_blocked_until = now_ts + SEND_BACKOFF_S
                self._complain("send", f"F1: versturen naar {self.channel} mislukt (bestaat het kanaal op de radio?)")
                return False
        return True

    def _radio_name_problem(self) -> str:
        """A hashtag channel's key is made from its lowercase name: '#F1' on the radio is another channel than '#f1'."""
        if not self.channel.startswith("#"):
            return ""
        try:
            info = self.bot.channel_manager.get_channel_by_name(self.channel)
        except Exception:  # noqa: BLE001
            return ""
        name = (info or {}).get("channel_name", "") or ""
        if name.startswith("#") and name != name.lower():
            return (f"F1: het kanaal op de radio heet '{name}' met een hoofdletter; dat is een ander kanaal dan {self.channel} "
                    f"dat anderen hebben. Maak het opnieuw aan met kleine letters. Er wordt niets gepost.")
        return ""

    async def _send(self, text: str) -> bool:
        cm = getattr(self.bot, "command_manager", None)
        if cm is None or not getattr(self.bot, "connected", False):
            return False
        wrong = self._radio_name_problem()
        if wrong:
            self._complain("name", wrong)
            return False
        # A post is not an answer to someone: like the notifications it must not use up the shared reply budget.
        limiter = getattr(self.bot, "rate_limiter", None)
        before = getattr(limiter, "last_send", None)
        try:
            return bool(await cm.send_channel_message(self.channel, text, skip_user_rate_limit=True))
        except Exception as e:  # noqa: BLE001
            self.logger.info("F1: verzenden mislukt: %s", e)
            return False
        finally:
            if before is not None:
                try:
                    with limiter._lock:
                        limiter.last_send = before
                except Exception:  # noqa: BLE001
                    pass

    async def _after_race(self, action: dict, now_ts: float) -> None:
        """Points for the prediction game, once per race, right after the result was posted."""
        if not (self.game_enabled and self.game):
            return
        try:
            scored = self.game.score(action["season"], action["round"], action["results"])
        except Exception as e:  # noqa: BLE001
            self._complain("game", f"F1: punten berekenen mislukt: {e}")
            return
        if not scored:
            return
        good = [f"{n} ({p} pt)" for n, _pick, p in scored if p > 0]
        head = self.translate("commands.f1.game_result_header", n=len(scored))
        parts = [
            self.translate("commands.f1.game_good", names=", ".join(good[:6]))
            if good else self.translate("commands.f1.game_none_good")
        ]
        table = self.game.standings(action["season"], 5)
        if table:
            parts.append(
                self.translate("commands.f1.game_standing")
                + " | ".join(f"{i} {n} {pts}" for i, (n, pts, _r) in enumerate(table, 1))
            )
        await self._post(F.pack(head, parts), now_ts)

    # ------------------------------------------------------------------ memory
    def _load_state(self) -> None:
        try:
            raw = self.bot.db_manager.get_metadata(STATE_KEY)
            data = json.loads(raw) if raw else {}
            if isinstance(data, dict):
                self.st = {"posted": list(data.get("posted", [])), "track": data.get("track"), "last_positions": data.get("last_positions"),
                           "last_live_ts": float(data.get("last_live_ts", 0) or 0)}
        except Exception as e:  # noqa: BLE001
            self.logger.debug("F1: staat lezen mislukt: %s", e)

    def _mark(self, key: str) -> None:
        posted = self.st.setdefault("posted", [])
        if key not in posted:
            posted.append(key)
        del posted[:-MAX_POSTED_KEYS]

    def _save_state(self) -> None:
        try:
            self.bot.db_manager.set_metadata(STATE_KEY, json.dumps(self.st))
        except Exception as e:  # noqa: BLE001
            self._complain("state", f"F1: staat opslaan mislukt: {e}")

    # ------------------------------------------------------------------ for the command
    def lock_ts(self) -> Optional[float]:
        """The prediction closes when the first qualifying session of the weekend starts."""
        nxt = self.snapshot.get("next")
        if not nxt:
            return None
        return nxt["sessions"].get("sq") or nxt["sessions"].get("quali")

    def valid_codes(self) -> set:
        return {d["code"] for d in self.snapshot.get("drivers", []) if d.get("code")}
