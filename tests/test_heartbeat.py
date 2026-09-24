"""Heartbeat: one sensor in Home Assistant, kept up to date, set to 'stopped' on a clean stop."""
import asyncio
import configparser
import logging
import os
import pathlib as _pl
import sys
import time
import types

_TESTS = _pl.Path(__file__).resolve().parent
TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
from aiohttp import web

from modules.service_plugins import heartbeat_service as hb
from modules.service_plugins.heartbeat_service import HeartbeatService

fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, r):
        self.records.append((r.levelname, r.getMessage()))


def make_bot(extra=None, connected=True):
    cfg = configparser.ConfigParser()
    if extra is not None:
        cfg["Heartbeat"] = {"enabled": "true", **extra}
    log = logging.getLogger(f"hb{time.time_ns()}")
    cap = Capture()
    log.addHandler(cap)
    log.setLevel(logging.DEBUG)
    return types.SimpleNamespace(config=cfg, logger=log, connected=connected,
                                 channel_manager=types.SimpleNamespace(_channels_cache={0: {}, 4: {}, 6: {}})), cap


state = {"status": 200, "calls": []}


async def handler(request):
    body = await request.json()
    state["calls"].append({"path": request.path, "auth": request.headers.get("Authorization"), "body": body})
    return web.Response(status=state["status"], text="{}")


async def main():
    app = web.Application()
    app.router.add_post("/states/{entity:.+}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    hb.STATES_URL = f"http://127.0.0.1:{port}/states/"
    os.environ["SUPERVISOR_TOKEN"] = "test-token"
    os.environ["ADDON_VERSION"] = "2.11.0"

    bot, cap = make_bot({})
    s = HeartbeatService(bot)
    check(s.interval == 300 and s.entity_id == "sensor.meshcore_bot_heartbeat", "standaard: elke 5 minuten naar sensor.meshcore_bot_heartbeat")
    await s.start()
    s._task.cancel()
    ok = await s.beat()
    c = state["calls"][-1]
    print("   ", c["path"], c["body"]["state"], c["body"]["attributes"])
    check(ok and c["path"] == "/states/sensor.meshcore_bot_heartbeat" and c["auth"] == "Bearer test-token", "schrijft de sensor met de Supervisor-token")
    a = c["body"]["attributes"]
    check(c["body"]["state"] == "online" and a["version"] == "2.11.0" and a["radio_connected"] is True and a["channels"] == 3 and a["uptime_s"] >= 0, "status online met versie, radio en aantal kanalen")
    check(a["last_beat"].endswith("+00:00") and a["friendly_name"] == "MeshCore Bot heartbeat", "tijdstip in UTC en een leesbare naam")

    bot2, _ = make_bot({}, connected=False)
    s2 = HeartbeatService(bot2)
    s2._session = s._session
    await s2.beat()
    check(state["calls"][-1]["body"]["state"] == "radio_offline" and state["calls"][-1]["body"]["attributes"]["radio_connected"] is False, "bot draait maar de radio is weg: 'radio_offline'")

    # errors never crash and are logged once
    state["status"] = 401
    check(await s.beat() is False and "toegang" in s.last_error, "HTTP 401: melding over homeassistant_api, geen crash")
    n = len(cap.records)
    await s.beat()
    await s.beat()
    check(len(cap.records) == n, "dezelfde fout wordt niet steeds opnieuw gelogd")
    state["status"] = 500
    check(await s.beat() is False and "500" in s.last_error, "HTTP 500: nette fout")
    state["status"] = 200
    check(await s.beat() is True and s.last_error == "" and s.last_beat > 0, "herstel zodra Home Assistant weer antwoordt")

    # a clean stop
    n_calls = len(state["calls"])
    await s.stop()
    check(len(state["calls"]) == n_calls + 1 and state["calls"][-1]["body"]["state"] == "stopped", "een nette stop zet de sensor op 'stopped' (geen storing)")

    # settings
    bot3, _ = make_bot({"interval_minutes": "60", "entity_id": "sensor.mijn_bot"})
    s3 = HeartbeatService(bot3)
    check(s3.interval == 1800 and s3.entity_id == "sensor.mijn_bot", "interval begrensd op 30 minuten, eigen sensornaam")
    bot4, _ = make_bot({"interval_minutes": "0", "entity_id": "light.iets"})
    s4 = HeartbeatService(bot4)
    check(s4.interval == 60 and s4.entity_id == "sensor.meshcore_bot_heartbeat", "interval minstens 1 minuut; een naam die geen sensor is valt terug op de standaard")
    bot5, _ = make_bot({"interval_minutes": "abc"})
    check(HeartbeatService(bot5).interval == 300, "onleesbaar interval: standaard")
    check(len(HeartbeatService.settings_schema) == 2, "kaart met twee velden")
    await runner.cleanup()
    print(f"\n{len(fails)} fouten")
    sys.exit(1 if fails else 0)


asyncio.run(main())
