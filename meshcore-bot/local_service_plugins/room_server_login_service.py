"""Room server login service plugin.

Logs the bot into a MeshCore room server (e.g. "My Room") at startup and
re-logs-in every `relogin_minutes` minutes (card setting, default 60) to keep the session alive, since the exact
session lifetime isn't documented anywhere accessible - a conservative fixed
re-login beats guessing wrong and silently dropping out. Also re-logs-in
after any radio reconnect, since that likely drops the session too.

No new message-handling code: once logged in, incoming room messages arrive
as ordinary CONTACT_MSG_RECV events - modules/message_handler.py's
handle_contact_message() already turns those into MeshMessage(is_dm=True,
...), which runs through the exact same command pipeline as a DM. Replies
use the existing send_dm() (command_manager.py), which already resolves
the room as a known contact. So this service's only job is keeping the
login itself alive; if that assumption turns out wrong in practice (e.g. the
sender identity arriving isn't what a DM-based ACL check expects), that's a
follow-up fix informed by what actually shows up in the logs - not something
to guess and build in speculatively here.

Config (config.ini):

    [RoomServer_Login]
    enabled = true
    public_key = <64 hex characters, the room server's public key>
    password = <room server password>
    relogin_minutes = 60     ; 15..720; every login is a message on the mesh, and it also refreshes the room's data
    admin_password =         ; optional: log in as admin, so the bot can keep the room's clock right
    clock_sync = true        ; after a login: check the room's clock and, as admin, run "clock sync" when it is off

The room's clock matters: the room stamps every post with its own time, and a client only fetches posts newer than
what it already has. A room whose clock fell back (a restart without GPS or time set) therefore keeps accepting posts
that nobody ever receives. Since firmware 1.10 the login reply carries the room's time, so the bot can see that; as
admin it sends the CLI command "clock sync", which sets the room's clock to the time of the command (the bot's, from
Home Assistant). MeshCore only lets "clock sync" move a clock forward, so a room that runs ahead is only reported.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from meshcore import EventType

from .base_service import BaseServicePlugin

DEFAULT_RELOGIN_MINUTES = 60
MIN_RELOGIN_MINUTES, MAX_RELOGIN_MINUTES = 15, 720
CLOCK_TOLERANCE_S = 120
ROOM_ADV_TYPE = 3          # meshcore AdvType.ROOM: a CLI command to a room goes as CLI_DATA


def clock_action(server_ts: Optional[int], now: float, is_admin: bool) -> tuple:
    """(what to do, drift in seconds) after a login. drift > 0: the room is behind.
    'sync' = send "clock sync"; 'behind' / 'ahead' = only report; 'ok' / 'unknown' = nothing to report."""
    if not server_ts:
        return ("sync" if is_admin else "unknown"), None
    drift = int(now - server_ts)
    if abs(drift) <= CLOCK_TOLERANCE_S:
        return "ok", drift
    if drift > 0:
        return ("sync" if is_admin else "behind"), drift
    return "ahead", drift


def human(seconds: int) -> str:
    seconds = abs(int(seconds))
    if seconds >= 86400:
        return f"{seconds // 86400} dag(en)"
    if seconds >= 3600:
        return f"{seconds // 3600} uur"
    return f"{max(1, seconds // 60)} min"


class RoomServerLoginService(BaseServicePlugin):
    config_section = "RoomServer_Login"

    # Settings card on the dashboard's Plugins page (the add-on options for this moved here in 2.7.0).
    settings_schema = [
        {"key": "public_key", "label": "Room server public key", "type": "str", "default": "",
         "pattern": "([0-9a-fA-F]{64})?",
         "help": "The room's 64-character public key. The bot logs in at startup, on the interval below and after a radio reconnect."},
        {"key": "password", "label": "Room server password", "type": "password", "default": "",
         "help": "The guest password is enough to chat. Note: the room's clock must be right, or the bot ignores its messages."},
        {"key": "admin_password", "label": "Room admin password (optional)", "type": "password", "default": "",
         "help": ("With the admin password the bot logs in as admin and can set the room's clock right (see below). "
                  "Empty: the bot logs in with the password above and only reports a wrong clock in the log.")},
        {"key": "clock_sync", "label": "Keep the room's clock right", "type": "bool", "default": True,
         "help": ("After every login the bot compares the room's clock with its own. When it is more than 2 minutes behind "
                  "(and the bot is admin) it sends 'clock sync'. A room whose clock is behind keeps posts that nobody receives.")},
        {"key": "relogin_minutes", "label": "Log in again every", "type": "int", "default": DEFAULT_RELOGIN_MINUTES,
         "min": MIN_RELOGIN_MINUTES, "max": MAX_RELOGIN_MINUTES, "unit": "min",
         "help": "Every login is a message on the mesh (airtime). It keeps the session alive and refreshes what the dashboard shows of the room."},
    ]
    description = "Keeps the bot logged into a MeshCore room server so it can respond there like a DM"

    def __init__(self, bot: Any):
        super().__init__(bot)
        section = self.config_section
        cfg = bot.config
        has_section = cfg.has_section(section)
        self.login_enabled = cfg.getboolean(section, "enabled", fallback=False) if has_section else False
        self.public_key = (cfg.get(section, "public_key", fallback="") if has_section else "").strip()
        self.password = (cfg.get(section, "password", fallback="") if has_section else "")
        self.admin_password = (cfg.get(section, "admin_password", fallback="") if has_section else "")
        self.clock_sync = cfg.getboolean(section, "clock_sync", fallback=True) if has_section else True
        try:
            minutes = int(cfg.get(section, "relogin_minutes", fallback=str(DEFAULT_RELOGIN_MINUTES)) if has_section else DEFAULT_RELOGIN_MINUTES)
        except ValueError:
            minutes = DEFAULT_RELOGIN_MINUTES
        self.relogin_seconds = max(MIN_RELOGIN_MINUTES, min(MAX_RELOGIN_MINUTES, minutes)) * 60
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if not self.login_enabled or not self.public_key:
            self.logger.debug(
                "RoomServer_Login: uitgeschakeld of geen public_key ingesteld, service blijft uit"
            )
            self.enabled = False
            return
        self._running = True
        self._task = asyncio.create_task(self._login_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def on_transport_reconnected(self) -> None:
        """A radio reconnect likely dropped the room-server session too."""
        if self.login_enabled and self.public_key:
            await self._login_once()

    async def _login_loop(self) -> None:
        while self._running:
            await self._login_once()
            await asyncio.sleep(self.relogin_seconds)

    async def _login_once(self) -> None:
        try:
            meshcore = getattr(self.bot, "meshcore", None)
            if meshcore is None:
                self.logger.warning(
                    "RoomServer_Login: geen actieve meshcore-verbinding, login overgeslagen"
                )
                return
            password = self.admin_password or self.password
            result = await meshcore.commands.send_login_sync(self.public_key, password)
            if result is not None and getattr(result, "type", None) == EventType.LOGIN_SUCCESS:
                payload = getattr(result, "payload", None) or {}
                is_admin = bool(payload.get("is_admin"))
                self.logger.info(
                    "RoomServer_Login: succesvol ingelogd op %s...%s", self.public_key[:12], " (als beheerder)" if is_admin else ""
                )
                if self.clock_sync:
                    await self._check_clock(meshcore, payload.get("server_timestamp"), is_admin)
            else:
                self.logger.warning(
                    "RoomServer_Login: inloggen op %s... mislukt of geen bevestiging ontvangen "
                    "(verkeerd wachtwoord? room server niet bereikbaar?) - result=%s",
                    self.public_key[:12], result,
                )
        except Exception as e:
            self.logger.warning("RoomServer_Login: fout bij inloggen: %s", e, exc_info=True)

    async def _check_clock(self, meshcore: Any, server_ts: Optional[int], is_admin: bool) -> None:
        """After a login: report a wrong room clock and, as admin, set it right with "clock sync"."""
        action, drift = clock_action(server_ts, time.time(), is_admin)
        if action == "ok":
            self.logger.debug("RoomServer_Login: klok van de room klopt (verschil %ss)", drift)
            return
        if action == "unknown":
            self.logger.debug("RoomServer_Login: de room stuurt geen tijd mee (oudere firmware), klok niet gecontroleerd")
            return
        if action == "ahead":
            self.logger.warning("RoomServer_Login: klok van de room loopt %s vóór; 'clock sync' kan een klok niet "
                                "terugzetten, zet hem in de MeshCore-app gelijk", human(drift))
            return
        if action == "behind":
            self.logger.warning("RoomServer_Login: klok van de room loopt %s achter, dus berichten komen niet aan; vul op de "
                                "kaart het admin-wachtwoord in, dan zet de bot hem gelijk", human(drift))
            return
        try:
            await meshcore.commands.send_cmd(self.public_key, "clock sync", dst_type=ROOM_ADV_TYPE)
            if drift is None:
                self.logger.info("RoomServer_Login: 'clock sync' naar de room gestuurd (room stuurt zelf geen tijd mee)")
            else:
                self.logger.warning("RoomServer_Login: klok van de room liep %s achter, 'clock sync' gestuurd", human(drift))
        except Exception as e:  # noqa: BLE001
            self.logger.warning("RoomServer_Login: 'clock sync' versturen mislukt: %s", e)

