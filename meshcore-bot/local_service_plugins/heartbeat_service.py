#!/usr/bin/env python3
"""Heartbeat: the bot tells Home Assistant every few minutes that it is alive (card: Plugins -> Heartbeat).

Everything the bot reports about itself (notifications, radio problems) comes from the bot, so when the whole add-on is down
nothing reports that. This service turns it round: it keeps ONE sensor in Home Assistant up to date, and Home Assistant raises
the alarm when that sensor has not been updated for a while (see the documentation for the automation).

It writes a single state (`sensor.meshcore_bot_heartbeat`, name is a setting) through Home Assistant's REST API with the
add-on's own permission (`homeassistant_api`). It never touches the radio. A clean stop sets the state to `stopped`; a crash
or a dead add-on simply stops the updates, which is exactly what the automation looks for.

State: `online`, or `radio_offline` when the bot runs but has no radio. Attributes: version, uptime_s, radio_connected,
channels, last_beat.
"""
import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

from .base_service import BaseServicePlugin

STATES_URL = "http://supervisor/core/api/states/"
FIRST_BEAT_DELAY_S = 15
ERROR_LOG_INTERVAL_S = 6 * 3600
ENTITY_PREFIX = "sensor."


class HeartbeatService(BaseServicePlugin):
    config_section = "Heartbeat"
    name = "heartbeat"
    description = "Keeps one sensor in Home Assistant up to date so Home Assistant can raise the alarm when the bot goes silent"

    settings_schema = [
        {"key": "interval_minutes", "label": "Update the sensor every", "type": "int", "default": 5, "min": 1, "max": 30, "unit": "min",
         "help": "Set the alarm in Home Assistant to a few times this (for example 15 minutes for 5)."},
        {"key": "entity_id", "label": "Sensor in Home Assistant", "type": "str", "default": "sensor.meshcore_bot_heartbeat",
         "pattern": "sensor\\.[a-z0-9_]{1,60}", "help": "Must start with sensor. and use only lowercase letters, digits and underscores."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        s = self.config_section
        has = cfg.has_section(s)

        def get(key, fallback=""):
            return cfg.get(s, key, fallback=fallback) if has else fallback

        try:
            minutes = int(get("interval_minutes", "5") or 5)
        except ValueError:
            minutes = 5
        self.interval = max(1, min(30, minutes)) * 60
        entity = (get("entity_id", "sensor.meshcore_bot_heartbeat") or "").strip().lower()
        self.entity_id = entity if entity.startswith(ENTITY_PREFIX) and len(entity) > len(ENTITY_PREFIX) else "sensor.meshcore_bot_heartbeat"
        self.started_at = time.time()
        self.last_beat: float = 0.0
        self.last_error = ""
        self._task: Optional[asyncio.Task] = None
        self._session = None
        self._error_logged: dict = {}

    async def start(self) -> None:
        if aiohttp is None:
            self.logger.warning("Heartbeat: aiohttp ontbreekt, service niet gestart")
            return
        self._running = True
        self.started_at = time.time()
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        self._task = asyncio.get_running_loop().create_task(self._loop())
        self.logger.info("Heartbeat: gestart (elke %d min naar %s)", self.interval // 60, self.entity_id)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._session is not None:
            try:
                await asyncio.wait_for(self.beat(state="stopped"), timeout=5)   # a clean stop is not an outage
            except Exception:  # noqa: BLE001
                pass
            await self._session.close()
            self._session = None

    async def _loop(self) -> None:
        await asyncio.sleep(FIRST_BEAT_DELAY_S)
        while self._running:
            try:
                await self.beat()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self._complain("loop", f"Heartbeat: mislukt: {e}")
            await asyncio.sleep(self.interval)

    def _complain(self, kind: str, text: str) -> None:
        self.last_error = text
        now = time.time()
        if now - self._error_logged.get(kind, 0.0) >= ERROR_LOG_INTERVAL_S:
            self._error_logged[kind] = now
            self.logger.warning(text)

    def payload(self, state: Optional[str] = None) -> dict:
        connected = bool(getattr(self.bot, "connected", False))
        channels = 0
        try:
            channels = len(getattr(getattr(self.bot, "channel_manager", None), "_channels_cache", {}) or {})
        except Exception:  # noqa: BLE001
            channels = 0
        return {
            "state": state or ("online" if connected else "radio_offline"),
            "attributes": {
                "friendly_name": "MeshCore Bot heartbeat", "icon": "mdi:radio-tower",
                "version": os.environ.get("ADDON_VERSION", ""), "uptime_s": int(time.time() - self.started_at),
                "radio_connected": connected, "channels": channels,
                "last_beat": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        }

    async def beat(self, state: Optional[str] = None) -> bool:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        try:
            async with self._session.post(STATES_URL + self.entity_id, json=self.payload(state),
                                          headers={"Authorization": f"Bearer {token}"}) as resp:
                if resp.status in (200, 201):
                    self.last_beat = time.time()
                    self.last_error = ""
                    return True
                if resp.status in (401, 403):
                    self._complain("auth", f"Heartbeat: geen toegang tot de Home Assistant-API (HTTP {resp.status})")
                else:
                    self._complain("http", f"Heartbeat: Home Assistant antwoordde HTTP {resp.status}")
        except asyncio.TimeoutError:
            self._complain("timeout", "Heartbeat: Home Assistant antwoordt niet (time-out)")
        except Exception as e:  # noqa: BLE001
            self._complain("net", f"Heartbeat: Home Assistant niet bereikbaar: {e}")
        return False
