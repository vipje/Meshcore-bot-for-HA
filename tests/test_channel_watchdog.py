"""Simuleert de storing van 2026-09-20 tegen de gepatchte upstream channel_manager."""
import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import asyncio, json, logging, sys, types, configparser

sys.path.insert(0, os.environ["SIM_TREE"])
sys.modules["meshcore"] = types.SimpleNamespace(EventType=types.SimpleNamespace(CHANNEL_INFO="x"))
from modules.channel_manager import ChannelManager

FULL = {0: "Public", 1: "Home Bot", 2: "Team Bot", 3: "Mesh|HA|🤖", 4: "#bot", 5: "#p2000-zl", 8: "#test"}
KEY = "channels.last_known"


class Res:
    def __init__(self, p): self.payload = p


class Commands:
    def __init__(self, radio): self.busy = False; self.radio = radio
    async def get_channel(self, idx):
        if self.busy:
            await asyncio.Event().wait()  # hangt tot wait_for hem afkapt -> timeout
        name = self.radio.get(idx)
        if not name:
            return Res({"channel_idx": idx, "channel_name": "", "channel_secret": b"\x00" * 16})
        return Res({"channel_idx": idx, "channel_name": name, "channel_secret": bytes([idx + 1]) * 16})


class DB:
    """Geheugen-metadata zoals bot_metadata; channels-tabel bestaat niet in de test."""
    def __init__(self, store): self.store = store
    def get_metadata(self, k): return self.store.get(k)
    def set_metadata(self, k, v): self.store[k] = v
    def connection(self): raise RuntimeError("geen tabel in test")


real_sleep = asyncio.sleep
slept = []


async def fast_sleep(d, *a):
    slept.append(d)
    await real_sleep(0 if d >= 1 else d)


def make(store, radio, monitor='"Team Bot,#test,#bot,#p2000-zl"'):
    cfg = configparser.ConfigParser()
    cfg["Channels"] = {"monitor_channels": monitor}
    cfg["Connection"] = {"channel_fetch_interval_ms": "0", "channel_recheck_minutes": "60"}
    bot = types.SimpleNamespace(
        logger=logging.getLogger("t"), config=cfg, connected=True, db_manager=DB(store),
        meshcore=types.SimpleNamespace(commands=Commands(radio), channels={}),
    )
    cm = ChannelManager(bot)
    cm._fetch_timeout = 0.01
    return cm, bot


async def settle(cm, cond, n=200):
    for _ in range(n):
        await real_sleep(0.005)
        if cond():
            return True
    return False


async def main():
    logging.basicConfig(level=logging.WARNING, format="   log: %(message)s")
    asyncio.sleep = fast_sleep

    # --- A. drukke radio bij de start; eerdere gezonde run staat in de opslag
    store = {KEY: json.dumps({str(k): v for k, v in FULL.items()})}
    cm, bot = make(store, FULL)
    bot.meshcore.commands.busy = True
    await cm.fetch_channels()
    print("A1 start (radio druk)  cache:", sorted(cm._channels_cache))
    assert cm._channels_cache == {}
    assert len(cm._missing_expected_channels()) == 7          # monitor + opgeslagen lijst
    assert json.loads(store[KEY]) == {str(k): v for k, v in FULL.items()}, "gedeeltelijke scan overschreef de lijst"
    bot.meshcore.commands.busy = False
    assert await settle(cm, lambda: not cm._missing_expected_channels())
    print("A2 na eerste controle  cache:", sorted(cm._channels_cache))
    assert sorted(cm._channels_cache) == [0, 1, 2, 3, 4, 5, 8]
    assert bot.meshcore.channels is cm._channels_cache
    cm._stop_channel_watchdog()

    # --- B. #bot valt later uit de cache: het uurlijkse rondje zet hem terug
    cm._channels_cache.pop(4)
    task = cm._channel_watchdog_task = asyncio.get_running_loop().create_task(cm._channel_watchdog())
    assert await settle(cm, lambda: 4 in cm._channels_cache)
    print("B  uurcheck herstelt #bot; wachttijden:", [d for d in slept if d >= 30][:5])
    assert 3600 in slept
    task.cancel()

    # --- C. gebruiker haalt 'Home Bot' (niet in monitor_channels) van de radio
    radio_c = {k: v for k, v in FULL.items() if k != 1}
    cm, bot = make(store, radio_c)
    await cm.fetch_channels()
    print("C1 na start zonder Home Bot, ontbreekt:", cm._missing_expected_channels())
    assert cm._missing_expected_channels() == ["Home Bot"]
    assert "Home Bot" in store[KEY], "lijst mag pas veranderen als het klopt"
    assert await settle(cm, lambda: "home bot" in getattr(cm, "_forgotten_channels", set()), n=400)
    assert not cm._missing_expected_channels()
    print("C2 vergeten na", cm._FORGET_AFTER_ROUNDS, "controles; opgeslagen lijst:", list(json.loads(store[KEY]).values()))
    assert "Home Bot" not in store[KEY]
    cm._stop_channel_watchdog()

    # --- D. een kanaal uit monitor_channels wordt nooit vergeten
    radio_d = {k: v for k, v in FULL.items() if k != 4}
    cm, bot = make({}, radio_d)
    await cm.fetch_channels()
    await settle(cm, lambda: False, n=100)
    print("D  #bot weg van radio maar in monitor_channels, blijft verwacht:", cm._missing_expected_channels())
    assert cm._missing_expected_channels() == ["#bot"]
    cm._stop_channel_watchdog()

    # --- E. herstart: oude taak stopt, geen dubbele taken
    cm, bot = make({}, FULL)
    await cm.fetch_channels()
    old = cm._channel_watchdog_task
    await cm.fetch_channels()
    await real_sleep(0.01)
    assert cm._channel_watchdog_task is not old and old.cancelled()
    cm._stop_channel_watchdog()
    print("E  herstart vervangt de taak")
    print("ALLES OK")

asyncio.run(main())
