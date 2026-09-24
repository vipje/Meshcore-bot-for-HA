#!/usr/bin/env python3
"""Repeater data from Home Assistant: battery, uptime, airtime, neighbours (card: Plugins -> HARepeater).

meshcore-ha polls the repeaters over the radio and publishes what it gets as Home Assistant sensors. This
service only READS those sensors from Home Assistant (`GET /api/states`, no password: the add-on's own
Supervisor token, `homeassistant_api: true`). It never sends anything over the radio and never writes to
Home Assistant, so it costs no airtime; how fresh the data is depends on how often meshcore-ha refreshes the
repeater (Settings -> Devices -> MeshCore -> Configure -> repeater -> Telemetry Refresh Rate).

It provides:
- the snapshot behind the `rptr` command (`service.repeaters`, `service.current()`);
- a history for graphs and troubleshooting: table `repeater_telemetry` (one row per new status reply) and
  `ha_repeater_neighbors` (the neighbour list of that reply), kept `keep_days` days;
- one warning per repeater per day when the battery drops below `low_battery_mv`, which the Notifications
  service passes on (see the `repeater` event there).
"""
import asyncio
import os
import time
from typing import Any, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

from .base_service import BaseServicePlugin

# Imported as a module of the bot (local_shared/ha_repeater_parser.py is copied to modules/).
try:
    from ..ha_repeater_parser import duration, parse_states, select
except ImportError:  # pragma: no cover - unit tests import the file directly
    from ha_repeater_parser import duration, parse_states, select   # type: ignore[no-redef]

STATES_URL = "http://supervisor/core/api/states"
FIRST_READ_DELAY_S = 10
LOW_BATTERY_INTERVAL_S = 24 * 3600
MAX_DATA_AGE_FOR_ALARM_S = 6 * 3600     # do not raise the alarm on a reading that is itself old news
ERROR_LOG_INTERVAL_S = 6 * 3600


class HARepeaterService(BaseServicePlugin):
    """Read-only bridge from meshcore-ha's repeater sensors."""

    config_section = "HARepeater"
    name = "harepeater"
    description = "Battery, uptime, airtime and neighbours of your repeaters, read from Home Assistant (no airtime)"

    settings_schema = [
        {"key": "repeaters", "label": "Repeaters to follow", "type": "list", "default": [],
         "pattern": "[0-9a-fA-F]{4,64}",
         "help": ("Empty = every repeater meshcore-ha knows. Otherwise the first characters of the repeater's public key, "
                  "comma-separated (in the sensor names that is the 10 characters after meshcore_, for example a1b2c3d4e5). "
                  "Type rptr list in a direct message to see the ones that were found. A room server is only followed "
                  "when it is listed here.")},
        {"key": "read_interval_minutes", "label": "Read Home Assistant every", "type": "int", "default": 5,
         "min": 1, "max": 60, "unit": "min",
         "help": ("Reading costs no airtime. How fresh the data is depends on meshcore-ha, not on this value: set how often it asks the "
                  "repeater in Home Assistant (Devices -> MeshCore -> Configure -> Telemetry Refresh Rate). Each request over the "
                  "radio costs airtime; a sensible upper limit is about one status request per hour per repeater.")},
        {"key": "low_battery_notify", "label": "Warn when the battery is low", "type": "bool", "default": True,
         "help": "One message per repeater per day, sent through the Notifications card (it must be switched on there)."},
        {"key": "low_battery_mv", "label": "Battery is low below", "type": "int", "default": 3600,
         "min": 3000, "max": 4200, "unit": "mV", "help": "For a single Li-ion cell 3600 mV (3.6 V) is about 10-15% left."},
        {"key": "alert_reboot", "label": "Warn when a repeater restarts", "type": "bool", "default": True,
         "help": "Its uptime dropped since the last reading (a crash, a power cut or a firmware update)."},
        {"key": "alert_offline", "label": "Warn when a repeater stops answering", "type": "bool", "default": True,
         "help": "meshcore-ha reports the repeater as offline for two readings in a row."},
        {"key": "alert_noise", "label": "Warn when the noise floor jumps", "type": "bool", "default": True,
         "help": "Interference near the repeater: the noise floor is clearly higher than its recent readings."},
        {"key": "noise_jump_db", "label": "Noise floor jump that counts", "type": "int", "default": 8, "min": 3, "max": 40, "unit": "dB"},
        {"key": "alert_airtime", "label": "Warn when the airtime is high", "type": "bool", "default": True,
         "help": "The repeater spends more than the percentage below of its time transmitting."},
        {"key": "airtime_max_pct", "label": "Airtime that counts as high", "type": "int", "default": 10, "min": 1, "max": 100, "unit": "%"},
        {"key": "alert_neighbors", "label": "Warn when a neighbour disappears", "type": "bool", "default": False,
         "help": "A neighbour that was in the last two neighbour lists is missing now. Off by default: mobile nodes come and go."},
        {"key": "keep_days", "label": "Keep the history for", "type": "int", "default": 365,
         "min": 7, "max": 3650, "unit": "days",
         "help": "Tables repeater_telemetry and ha_repeater_neighbors in the bot's database."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        s = self.config_section
        has = cfg.has_section(s)

        def get(key, fallback=""):
            return cfg.get(s, key, fallback=fallback) if has else fallback

        self.wanted = [w.strip().lower() for w in get("repeaters").split(",") if w.strip()]
        self.interval = max(1, min(60, int(get("read_interval_minutes", "5") or 5))) * 60
        self.low_notify = cfg.getboolean(s, "low_battery_notify", fallback=True) if has else True
        self.low_mv = int(get("low_battery_mv", "3600") or 3600)
        self.keep_days = max(7, int(get("keep_days", "365") or 365))

        def flag(key, fallback):
            return cfg.getboolean(s, key, fallback=fallback) if has else fallback

        def number(key, fallback):
            try:
                return int(get(key, str(fallback)) or fallback)
            except ValueError:
                return fallback
        self.alert_reboot = flag("alert_reboot", True)
        self.alert_offline = flag("alert_offline", True)
        self.alert_noise = flag("alert_noise", True)
        self.alert_airtime = flag("alert_airtime", True)
        self.alert_neighbors = flag("alert_neighbors", False)
        self.noise_jump_db = number("noise_jump_db", 8)
        self.airtime_max_pct = number("airtime_max_pct", 10)
        self._offline_reads: dict = {}

        self.repeaters: dict = {}          # everything meshcore-ha knows, by 10-hex prefix
        self.last_read: float = 0.0
        self.last_error: str = ""
        self._task: Optional[asyncio.Task] = None
        self._session = None
        self._last_key: dict = {}          # prefix -> stats_key of the last stored reading
        self._error_logged: dict = {}
        self._retention_at = 0.0
        self._reported_found: tuple = ()

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if aiohttp is None:
            self.logger.warning("HARepeater: aiohttp ontbreekt, service niet gestart")
            return
        if not os.environ.get("SUPERVISOR_TOKEN"):
            self.logger.warning("HARepeater: geen SUPERVISOR_TOKEN (draait dit als add-on met homeassistant_api?)")
        self._running = True
        self._ensure_tables()
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
        self._task = asyncio.get_running_loop().create_task(self._loop())
        self.logger.info("HARepeater: gestart (elke %d min lezen uit Home Assistant, geen radio)", self.interval // 60)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _loop(self) -> None:
        await asyncio.sleep(FIRST_READ_DELAY_S)
        while self._running:
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - never let a bad reading stop the loop
                self._complain("loop", f"HARepeater: lezen mislukt: {e}")
            await asyncio.sleep(self.interval)

    # ------------------------------------------------------------------ reading
    async def _fetch(self) -> Optional[list]:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        try:
            async with self._session.get(STATES_URL, headers={"Authorization": f"Bearer {token}"}) as resp:
                if resp.status in (401, 403):
                    self._complain("auth", f"HARepeater: geen toegang tot de Home Assistant-API (HTTP {resp.status}); "
                                           "staat homeassistant_api aan voor deze add-on?")
                    return None
                if resp.status != 200:
                    self._complain("http", f"HARepeater: Home Assistant antwoordde HTTP {resp.status}")
                    return None
                return await resp.json(content_type=None)
        except asyncio.TimeoutError:
            self._complain("timeout", "HARepeater: Home Assistant antwoordt niet (time-out)")
        except Exception as e:  # noqa: BLE001
            self._complain("net", f"HARepeater: Home Assistant niet bereikbaar: {e}")
        return None

    def _complain(self, kind: str, text: str) -> None:
        """At most one warning per kind every ERROR_LOG_INTERVAL_S: a broken link must not fill the log."""
        self.last_error = text
        now = time.time()
        if now - self._error_logged.get(kind, 0.0) >= ERROR_LOG_INTERVAL_S:
            self._error_logged[kind] = now
            self.logger.warning(text)

    async def refresh(self) -> bool:
        states = await self._fetch()
        if states is None:
            return False
        self.repeaters = parse_states(states)
        self.last_read = time.time()
        self.last_error = ""
        chosen = select(self.repeaters, self.wanted)
        found = tuple(sorted((r["prefix"], r["name"], r in chosen) for r in self.repeaters.values()))
        if found != self._reported_found:      # once at the start, and again when something appears or disappears
            self._reported_found = found
            self.logger.info("HARepeater: %d apparaat(en) met batterijsensor gevonden in Home Assistant: %s", len(found),
                             ", ".join(f"{p} {n} ({'gevolgd' if f else 'niet gevolgd'})" for p, n, f in found) or "geen")
        self._alerts(chosen)      # compares with what is stored, so before the new reading is stored
        self._store(chosen)
        self._check_battery(chosen)
        self._retention()
        return True

    def current(self, selector: str = "") -> list:
        """The repeaters to report on; `selector` = part of a name or the first characters of a key."""
        chosen = select(self.repeaters, self.wanted)
        sel = (selector or "").strip().lower()
        if sel:
            chosen = [r for r in chosen if sel in r["name"].lower() or r["public_key"].startswith(sel) or r["prefix"].startswith(sel)]
        return chosen

    # ------------------------------------------------------------------ database
    def _ensure_tables(self) -> None:
        try:
            with self.bot.db_manager.connection() as conn:
                cur = conn.cursor()
                cur.execute("""CREATE TABLE IF NOT EXISTS repeater_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at INTEGER NOT NULL, repeater_key TEXT NOT NULL,
                    repeater_name TEXT, battery_mv INTEGER, battery_pct REAL, temperature REAL, ch1_voltage REAL,
                    uptime_s INTEGER, airtime_s INTEGER, airtime_util REAL, nb_recv INTEGER, nb_sent INTEGER,
                    noise_floor REAL, last_rssi REAL, last_snr REAL, neighbor_count INTEGER,
                    stats_key TEXT, source TEXT NOT NULL DEFAULT 'ha')""")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_repeater_telemetry_key_time ON repeater_telemetry (repeater_key, recorded_at)")
                cur.execute("""CREATE TABLE IF NOT EXISTS ha_repeater_neighbors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at INTEGER NOT NULL, repeater_key TEXT NOT NULL,
                    neighbor_prefix TEXT NOT NULL, neighbor_name TEXT, snr REAL, secs_ago INTEGER, stats_key TEXT)""")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_ha_repeater_neighbors_key_time ON ha_repeater_neighbors (repeater_key, recorded_at)")
                for key, stats_key in cur.execute(
                        "SELECT repeater_key, stats_key FROM repeater_telemetry WHERE id IN "
                        "(SELECT MAX(id) FROM repeater_telemetry GROUP BY repeater_key)").fetchall():
                    self._last_key[key] = stats_key
                conn.commit()
        except Exception as e:  # noqa: BLE001
            self.logger.warning("HARepeater: tabellen maken mislukt: %s", e)

    def _store(self, chosen: list) -> None:
        """One row per new status reply from a repeater (recognised by its stats_key), plus its neighbour list."""
        fresh = [r for r in chosen if r.get("battery_mv") is not None and r.get("stats_key")
                 and self._last_key.get(r["public_key"]) != r["stats_key"]]
        if not fresh:
            return
        now = int(time.time())
        try:
            with self.bot.db_manager.connection() as conn:
                cur = conn.cursor()
                for r in fresh:
                    cur.execute(
                        "INSERT INTO repeater_telemetry (recorded_at, repeater_key, repeater_name, battery_mv, battery_pct, temperature, "
                        "ch1_voltage, uptime_s, airtime_s, airtime_util, nb_recv, nb_sent, noise_floor, last_rssi, last_snr, "
                        "neighbor_count, stats_key, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ha')",
                        (now, r["public_key"], r["name"], r["battery_mv"], r.get("battery_pct"), r.get("temperature"), r.get("ch1_voltage"),
                         r.get("uptime_s"), r.get("airtime_s"), r.get("airtime_util"),
                         None if r.get("nb_recv") is None else int(r["nb_recv"]), None if r.get("nb_sent") is None else int(r["nb_sent"]),
                         r.get("noise_floor"), r.get("last_rssi"), r.get("last_snr"),
                         None if r.get("neighbor_count") is None else int(r["neighbor_count"]), r["stats_key"]))
                    for n in r["neighbors"]:
                        cur.execute("INSERT INTO ha_repeater_neighbors (recorded_at, repeater_key, neighbor_prefix, neighbor_name, snr, "
                                    "secs_ago, stats_key) VALUES (?,?,?,?,?,?,?)",
                                    (now, r["public_key"], n["prefix"], n["name"], n["snr"], n["secs_ago"], r["stats_key"]))
                conn.commit()
            for r in fresh:
                self._last_key[r["public_key"]] = r["stats_key"]
        except Exception as e:  # noqa: BLE001
            self._complain("db", f"HARepeater: opslaan mislukt: {e}")

    def _retention(self) -> None:
        now = time.time()
        if now - self._retention_at < 24 * 3600:
            return
        self._retention_at = now
        cutoff = int(now - self.keep_days * 86400)
        try:
            with self.bot.db_manager.connection() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM repeater_telemetry WHERE recorded_at < ?", (cutoff,))
                cur.execute("DELETE FROM ha_repeater_neighbors WHERE recorded_at < ?", (cutoff,))
                conn.commit()
        except Exception as e:  # noqa: BLE001
            self._complain("db", f"HARepeater: opschonen mislukt: {e}")

    # ------------------------------------------------------------------ history and alerts
    def battery_history(self, key: str, hours: int) -> list:
        """[(unix time, mV)] of the stored readings of one repeater, oldest first."""
        cutoff = int(time.time() - hours * 3600)
        try:
            with self.bot.db_manager.connection() as conn:
                return [(int(t), int(v)) for t, v in conn.execute(
                    "SELECT recorded_at, battery_mv FROM repeater_telemetry WHERE repeater_key=? AND recorded_at>=? AND battery_mv IS NOT NULL "
                    "ORDER BY recorded_at", (key, cutoff)).fetchall()]
        except Exception as e:  # noqa: BLE001
            self._complain("db", f"HARepeater: geschiedenis lezen mislukt: {e}")
            return []

    def _once(self, kind: str, prefix: str, gap_s: float) -> bool:
        """True (and remembered) at most once per `gap_s` per kind and repeater; survives a restart."""
        key = f"harepeater.alert.{kind}.{prefix}"
        now = time.time()
        try:
            last = float(self.bot.db_manager.get_metadata(key) or 0)
        except (TypeError, ValueError):
            last = 0.0
        if now - last < gap_s:
            return False
        try:
            self.bot.db_manager.set_metadata(key, str(now))
        except Exception:  # noqa: BLE001
            pass
        return True

    def _previous(self, key: str, n: int) -> list:
        try:
            with self.bot.db_manager.connection() as conn:
                return conn.execute("SELECT uptime_s, noise_floor, stats_key FROM repeater_telemetry WHERE repeater_key=? ORDER BY id DESC LIMIT ?",
                                    (key, n)).fetchall()
        except Exception:  # noqa: BLE001
            return []

    def _neighbours_of(self, key: str, stats_key: str) -> set:
        try:
            with self.bot.db_manager.connection() as conn:
                return {(str(p)[:6], n or "") for p, n in conn.execute(
                    "SELECT neighbor_prefix, neighbor_name FROM ha_repeater_neighbors WHERE repeater_key=? AND stats_key=?", (key, stats_key)).fetchall()}
        except Exception:  # noqa: BLE001
            return set()

    def _alerts(self, chosen: list) -> None:
        """Warnings in the log (the Notifications service passes them on): restart, offline, noise, airtime, neighbours."""
        for r in chosen:
            key, name, prefix = r["public_key"], r["name"], r["prefix"]
            # offline: needs no new reading, two reads in a row
            if self.alert_offline and r.get("online") is not None:
                self._offline_reads[prefix] = 0 if r["online"] else self._offline_reads.get(prefix, 0) + 1
                if self._offline_reads[prefix] == 2 and self._once("offline", prefix, 86400):
                    self.logger.warning("HARepeater: offline: %s reageert niet meer", name)
            fresh = r.get("battery_mv") is not None and r.get("stats_key") and self._last_key.get(key) != r["stats_key"]
            if not fresh:
                continue
            prev = self._previous(key, 7)
            if self.alert_reboot and prev and r.get("uptime_s") is not None and prev[0][0] is not None and r["uptime_s"] + 60 < prev[0][0]:
                if self._once("reboot", prefix, 3600):
                    self.logger.warning(
                        "HARepeater: herstart: %s (uptime nu %s, was %s)", name,
                        duration(r["uptime_s"], self.bot.translator.translate), duration(prev[0][0], self.bot.translator.translate),
                    )
            if self.alert_noise and r.get("noise_floor") is not None:
                base = sorted(p[1] for p in prev[:6] if p[1] is not None)
                if len(base) >= 3:
                    median = base[len(base) // 2]
                    if r["noise_floor"] - median >= self.noise_jump_db and self._once("noise", prefix, 86400):
                        self.logger.warning("HARepeater: ruisvloer hoog: %s %d dBm (was rond %d)", name, r["noise_floor"], median)
            if self.alert_airtime and r.get("airtime_util") is not None and r["airtime_util"] > self.airtime_max_pct:
                if self._once("airtime", prefix, 86400):
                    self.logger.warning("HARepeater: airtime hoog: %s %.0f%% (grens %d%%)", name, r["airtime_util"], self.airtime_max_pct)
            if self.alert_neighbors and len(prev) >= 2 and prev[0][2] and prev[1][2]:
                before = self._neighbours_of(key, prev[0][2]) & self._neighbours_of(key, prev[1][2])
                now_set = {str(n["prefix"])[:6] for n in r["neighbors"]}
                gone = sorted((label or p) for p, label in before if p not in now_set)
                if gone and self._once("neighbors", prefix, 86400):
                    self.logger.warning("HARepeater: buur weg: %s zag %s niet meer", name, ", ".join(gone[:2]) + (f" (+{len(gone) - 2})" if len(gone) > 2 else ""))

    # ------------------------------------------------------------------ low battery
    def _check_battery(self, chosen: list) -> None:
        """One warning per repeater per day; the Notifications service picks it up from the log."""
        if not self.low_notify:
            return
        now = time.time()
        for r in chosen:
            mv, age = r.get("battery_mv"), r.get("stats_age_s")
            if mv is None or mv >= self.low_mv or (age is not None and age > MAX_DATA_AGE_FOR_ALARM_S):
                continue
            key = f"harepeater.lowbat.{r['prefix']}"
            try:
                last = float(self.bot.db_manager.get_metadata(key) or 0)
            except (TypeError, ValueError):
                last = 0.0
            if now - last < LOW_BATTERY_INTERVAL_S:
                continue
            try:
                self.bot.db_manager.set_metadata(key, str(now))
            except Exception:  # noqa: BLE001
                pass
            pct = f" ({int(r['battery_pct'])}%)" if r.get("battery_pct") is not None else ""
            self.logger.warning("HARepeater: batterij laag: %s %.2f V%s (grens %.2f V)", r["name"], mv / 1000, pct, self.low_mv / 1000)
