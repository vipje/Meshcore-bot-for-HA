#!/usr/bin/env python3
"""Source patch applied to the vendored meshcore-bot channel discovery.

Runs once during the Docker build, right after `git clone` (see
patch_webviewer.py for the shared rationale/mechanics). Applies next to
patch_channel_manager.py; the two touch different lines.

(Adapted for upstream v1.1.0: the scan is wrapped instead of edited, see step 2 below.)

Problem: the scan of the radio's channels at startup waits only 2 s per
channel and cannot tell a timeout from an empty slot. When the radio is busy
at that moment (Home Assistant's meshcore-ha is loading its contacts and
channels through the proxy right after a reboot), the bot's requests wait in
the proxy queue, time out, and count as "empty". Result seen on 2026-09-20:
after an HA restart only 1 of 4 monitored channels was loaded (#test), the
bot silently stopped answering in #bot until the next restart
("Channel 4 not found in cached channels"). Upstream also wipes its own
`channels` table on every scan, so that table cannot be used to notice this.

Changes:
1. Per-channel timeout 2 s -> 6 s. A truly empty slot still answers at once,
   so a normal start is not slower.
2. The bot remembers the channels it saw the last time everything was fine
   (`bot_metadata` key `channels.last_known`, JSON {index: name}). Expected
   channels = [Channels] monitor_channels + that list.
3. A background check (`_channel_watchdog`) after every channel scan compares
   the expected channels with the channel cache: after 30 s, 60 s and 120 s,
   and then every `[Connection] channel_recheck_minutes` minutes (default 60,
   0 = only the three startup checks). When one is missing it asks the radio
   again, only for the slots that are not in the cache yet, without clearing
   the cache, so channels that work keep working during the scan. When nothing
   is missing the check costs no radio traffic.
4. A channel that is only in the remembered list (not in monitor_channels) and
   is still missing after 5 checks (the 3 startup ones and 2 hourly ones) is
   forgotten, so a channel you removed from the radio does not warn forever.
   A channel in monitor_channels is never forgotten (that is a setting).
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")


CM = "modules/channel_manager.py"

# 1. Longer per-channel timeout.
patch(
    CM,
    "        self._fetch_timeout = 2.0  # Timeout for individual channel fetches",
    "        self._fetch_timeout = 6.0  # Timeout for individual channel fetches"
    " (was 2.0: too short while another client holds the proxy's turn)",
)

# 2. Upstream v1.1.0 already retries the scan when the radio returns nothing at all
#    (fetch_channels, 3 attempts). It does not notice a scan that returns only part of the
#    channels, which is what happened on 2026-09-20. Wrap it: stop an older watchdog when a new
#    scan starts (reconnect), and start the watchdog once the scan is done, also after a failed one.
patch(
    CM,
    "    async def fetch_channels(self, max_attempts: int = 3, retry_delay: float = 2.0) -> bool:\n",
    "    async def fetch_channels(self, *args, **kwargs):\n"
    '        """Upstream scan with retries, followed by the channel watchdog (patch_channel_watchdog.py)."""\n'
    "        self._stop_channel_watchdog()\n"
    "        try:\n"
    "            return await self._fetch_channels_with_retries(*args, **kwargs)\n"
    "        finally:\n"
    "            self._start_channel_watchdog()\n"
    "\n"
    "    async def _fetch_channels_with_retries(self, max_attempts: int = 3, retry_delay: float = 2.0) -> bool:\n",
)

# 2c. The watchdog itself.
WATCHDOG = '''    _SNAPSHOT_KEY = 'channels.last_known'
    _FORGET_AFTER_ROUNDS = 5

    def _monitored_channel_names(self) -> list[str]:
        """Names from [Channels] monitor_channels."""
        try:
            raw = self.bot.config.get('Channels', 'monitor_channels', fallback='')
        except Exception:
            return []
        return [c.strip() for c in raw.strip().strip('"\\'').split(',') if c.strip()]

    def _load_channel_snapshot(self) -> dict[str, str]:
        """Channels seen the last time everything was fine: {index: name}."""
        import json
        try:
            raw = self.bot.db_manager.get_metadata(self._SNAPSHOT_KEY)
            data = json.loads(raw) if raw else {}
            return {str(k): str(v) for k, v in data.items() if v}
        except Exception as e:
            self.logger.debug(f"Could not read the remembered channel list: {e}")
            return {}

    def _current_channel_snapshot(self) -> dict[str, str]:
        return {
            str(idx): c['channel_name']
            for idx, c in sorted(self._channels_cache.items())
            if c.get('channel_name')
        }

    def _save_channel_snapshot_if_changed(self) -> None:
        import json
        current = self._current_channel_snapshot()
        if not current or current == self._load_channel_snapshot():
            return
        try:
            self.bot.db_manager.set_metadata(self._SNAPSHOT_KEY, json.dumps(current, sort_keys=True))
            self.logger.info(f"Channel list remembered: {', '.join(current.values())}")
        except Exception as e:
            self.logger.warning(f"Could not remember the channel list: {e}")

    def _missing_expected_channels(self) -> list[str]:
        """Expected channels (monitor_channels + last known list) that are not in the cache."""
        norm = self._normalize_channel_name_for_lookup
        forgotten = getattr(self, '_forgotten_channels', set())
        wanted = list(self._monitored_channel_names())
        wanted += [n for n in self._load_channel_snapshot().values() if norm(n) not in forgotten]
        have = {norm(c['channel_name']) for c in self._channels_cache.values() if c.get('channel_name')}
        missing, seen = [], set()
        for name in wanted:
            key = norm(name)
            if key in have or key in seen:
                continue
            seen.add(key)
            missing.append(name)
        return missing

    async def _rescan_missing_channels(self) -> None:
        """Ask the radio again for every slot that is not in the cache (cache is not cleared)."""
        for channel_idx in range(self.max_channels):
            if channel_idx in self._channels_cache:
                continue
            result = await self._fetch_single_channel(channel_idx)
            if result and result.get("channel_name"):
                self._channels_cache[channel_idx] = result
                self._store_single_channel_in_db(result)
                self.logger.info(
                    f"Channel {channel_idx}: {result['channel_name']} (found by channel check)"
                )
            if not self._missing_expected_channels():
                break
            if self._fetch_interval > 0:
                await asyncio.sleep(self._fetch_interval)
        self.bot.meshcore.channels = self._channels_cache

    async def _channel_check(self, round_no: int) -> None:
        norm = self._normalize_channel_name_for_lookup
        missing = self._missing_expected_channels()
        if not missing:
            self._save_channel_snapshot_if_changed()
            return
        self.logger.warning(
            f"Channel check: channels not in the channel cache: {missing} - scanning again"
        )
        try:
            await self._rescan_missing_channels()
        except Exception as e:
            self.logger.warning(f"Channel check failed: {e}")
            return

        # Forget remembered channels that stay away, unless they are in monitor_channels.
        monitored = {norm(n) for n in self._monitored_channel_names()}
        rounds = self.__dict__.setdefault('_missing_rounds', {})
        forgotten = self.__dict__.setdefault('_forgotten_channels', set())
        still_missing = self._missing_expected_channels()
        for key in list(rounds):
            if key not in {norm(n) for n in still_missing}:
                del rounds[key]
        for name in still_missing:
            key = norm(name)
            if key in monitored:
                continue
            rounds[key] = rounds.get(key, 0) + 1
            if rounds[key] >= self._FORGET_AFTER_ROUNDS:
                forgotten.add(key)
                self.logger.info(f"Channel check: {name} is no longer on the radio, forgotten")
        still_missing = self._missing_expected_channels()

        if still_missing:
            self.logger.warning(f"Channel check: still missing after scan: {still_missing}")
        else:
            self.logger.info("Channel check: all expected channels are known")
            self._save_channel_snapshot_if_changed()

    async def _channel_watchdog(self) -> None:
        """Startup checks after 30/60/120 s, then every channel_recheck_minutes."""
        try:
            recheck_minutes = self.bot.config.getint(
                'Connection', 'channel_recheck_minutes', fallback=60
            )
        except Exception:
            recheck_minutes = 60
        startup_delays = [30, 60, 120]
        round_no = 0
        while True:
            if startup_delays:
                delay = startup_delays.pop(0)
            elif recheck_minutes > 0:
                delay = recheck_minutes * 60
            else:
                return
            await asyncio.sleep(delay)
            round_no += 1
            await self._channel_check(round_no)

    def _start_channel_watchdog(self) -> None:
        self._stop_channel_watchdog()
        missing = self._missing_expected_channels()
        if missing:
            self.logger.warning(
                f"Channels after the scan: not found: {missing} "
                "(compared with monitor_channels and the list from the last run)"
            )
        else:
            self._save_channel_snapshot_if_changed()
        try:
            self._channel_watchdog_task = asyncio.get_running_loop().create_task(
                self._channel_watchdog()
            )
        except RuntimeError:
            self._channel_watchdog_task = None

    def _stop_channel_watchdog(self) -> None:
        task = getattr(self, '_channel_watchdog_task', None)
        if task is not None and not task.done():
            task.cancel()
        self._channel_watchdog_task = None

'''
ANCHOR = "    async def fetch_all_channels(self, force_refresh: bool = False) -> list[dict[str, Any]]:\n"
patch(CM, ANCHOR, WATCHDOG + ANCHOR)
