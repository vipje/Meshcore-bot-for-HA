"""HARepeater-service tegen een nagebootste Home Assistant-server (aiohttp) en een echte sqlite-database."""
import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import asyncio, configparser, contextlib, logging, os, sqlite3, sys, tempfile, time, types
sys.path.insert(0, sys.argv[1]); os.chdir(sys.argv[1])
sys.path.insert(0, FIXTURES)
from aiohttp import web
import ha_states as F                       # herbruikt de fixture van de parsertest

from modules.service_plugins import ha_repeater_service as svc_mod
from modules.service_plugins.ha_repeater_service import HARepeaterService

fails = []
def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c: fails.append(m)

class DB:
    def __init__(self, path): self.path = path; self._c = sqlite3.connect(path); self._c.execute("CREATE TABLE IF NOT EXISTS bot_metadata (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)")
    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        try: yield c
        finally: c.close()
    def get_metadata(self, k):
        with self.connection() as c:
            r = c.execute("SELECT value FROM bot_metadata WHERE key=?", (k,)).fetchone(); return r[0] if r else None
    def set_metadata(self, k, v):
        with self.connection() as c:
            c.execute("INSERT OR REPLACE INTO bot_metadata (key, value) VALUES (?,?)", (k, v)); c.commit()

class Capture(logging.Handler):
    def __init__(self): super().__init__(); self.records = []
    def emit(self, r): self.records.append((r.levelname, r.getMessage()))

def make_bot(db, **cfg_extra):
    cfg = configparser.ConfigParser()
    cfg["HARepeater"] = {"enabled": "true", "read_interval_minutes": "5", "low_battery_notify": "true", "low_battery_mv": "3600", "keep_days": "30", **cfg_extra}
    log = logging.getLogger("t"); log.handlers = []; cap = Capture(); log.addHandler(cap); log.setLevel(logging.DEBUG)
    return types.SimpleNamespace(config=cfg, logger=log, db_manager=db), cap

state = {"payload": [], "status": 200, "auth": None, "calls": 0}
async def handler(request):
    state["calls"] += 1; state["auth"] = request.headers.get("Authorization")
    if state["status"] != 200: return web.Response(status=state["status"], text="nee")
    return web.json_response(state["payload"])

async def main():
    app = web.Application(); app.router.add_get("/states", handler)
    runner = web.AppRunner(app); await runner.setup(); site = web.TCPSite(runner, "127.0.0.1", 0); await site.start()
    port = site._server.sockets[0].getsockname()[1]
    svc_mod.STATES_URL = f"http://127.0.0.1:{port}/states"
    os.environ["SUPERVISOR_TOKEN"] = "test-token"
    tmp = tempfile.mkdtemp(); db = DB(f"{tmp}/bot.db")
    bot, cap = make_bot(db)
    NOW = time.time()

    def payload(stats_key="2026-09-21T18:30:00", mv=3920, age=900):
        st = F.repeater_states(NOW, stats_key, mv, age) + F.room_states(NOW)
        return st

    state["payload"] = payload()
    s = HARepeaterService(bot)
    check(s.interval == 300 and s.low_mv == 3600 and s.keep_days == 30 and s.wanted == [], "instellingen uit de sectie gelezen")
    await s.start()
    s._task.cancel()                                   # de lus zelf testen we niet; refresh() wel
    ok = await s.refresh()
    check(ok and state["auth"] == "Bearer test-token", "lezen lukt en stuurt de Supervisor-token mee")
    check(set(s.repeaters) == {F.PFX, "f6e5d4c3b2"} and [r["prefix"] for r in s.current()] == [F.PFX], "room server wordt gezien maar niet standaard gevolgd")
    with db.connection() as c:
        n1 = c.execute("SELECT COUNT(*) FROM repeater_telemetry").fetchone()[0]; nb = c.execute("SELECT COUNT(*) FROM ha_repeater_neighbors").fetchone()[0]
        row = c.execute("SELECT repeater_key, repeater_name, battery_mv, uptime_s, neighbor_count, source FROM repeater_telemetry").fetchone()
    check(n1 == 1 and nb == 4, f"één meting en 4 buren opgeslagen ({n1}, {nb})")
    check(row[0] == F.KEY and row[1] == F.NAME and row[2] == 3920 and row[3] == 1107330 and row[4] == 3 and row[5] == "ha", "rij bevat volledige sleutel, naam, mV, uptime, buren en bron 'ha'")

    await s.refresh()
    with db.connection() as c: check(c.execute("SELECT COUNT(*) FROM repeater_telemetry").fetchone()[0] == 1, "zelfde meting nogmaals lezen voegt niets toe")
    state["payload"] = payload(stats_key="2026-09-21T20:30:00", mv=3890)
    await s.refresh()
    with db.connection() as c: check(c.execute("SELECT COUNT(*) FROM repeater_telemetry").fetchone()[0] == 2, "nieuwe meting van de repeater geeft een nieuwe rij")
    s2 = HARepeaterService(bot); s2._ensure_tables()
    check(s2._last_key.get(F.KEY) == "2026-09-21T20:30:00", "na een herstart weet de service wat al is opgeslagen")
    s2._session = None
    await s.stop()

    # fouten van Home Assistant
    state["status"] = 401
    s3 = HARepeaterService(bot); await s3.start(); s3._task.cancel()
    check(await s3.refresh() is False and "toegang" in s3.last_error, "HTTP 401: melding over homeassistant_api, geen crash")
    before = len(cap.records); await s3.refresh(); await s3.refresh()
    check(len(cap.records) == before, "dezelfde fout wordt niet steeds opnieuw gelogd")
    state["status"] = 500; check(await s3.refresh() is False and "500" in s3.last_error, "HTTP 500: nette fout")
    state["status"] = 200; state["payload"] = payload(); check(await s3.refresh() is True and s3.last_error == "", "herstel: fout verdwijnt zodra Home Assistant weer antwoordt")
    await s3.stop()

    # lege lijst / geen repeaters
    state["payload"] = []
    s4 = HARepeaterService(bot); await s4.start(); s4._task.cancel()
    check(await s4.refresh() is True and s4.repeaters == {} and s4.current() == [], "Home Assistant zonder repeaters: leeg maar geen fout")
    await s4.stop()

    # lage batterij
    cap.records.clear(); state["payload"] = payload(mv=3500)
    s5 = HARepeaterService(bot); await s5.start(); s5._task.cancel()
    await s5.refresh()
    lows = [(lvl, m) for lvl, m in cap.records if "batterij laag" in m]
    check(len(lows) == 1 and lows[0][0] == "WARNING", f"lage batterij: één waarschuwing op niveau WARNING ({lows})")
    check(lows and "NL|XX|TOWN|RPTR|01" in lows[0][1] and "3.50 V" in lows[0][1] and "3.60 V" in lows[0][1], "waarschuwing noemt naam, spanning en grens")
    await s5.refresh(); await s5.refresh()
    check(len([m for _, m in cap.records if "batterij laag" in m]) == 1, "niet vaker dan één keer per dag")
    s6 = HARepeaterService(bot); s6._check_battery(s6.current() or s5.current())
    check(len([m for _, m in cap.records if "batterij laag" in m]) == 1, "ook na een herstart niet opnieuw (staat in de database)")
    db.set_metadata(f"harepeater.lowbat.{F.PFX}", str(time.time() - 90000)); await s5.refresh()
    check(len([m for _, m in cap.records if "batterij laag" in m]) == 2, "na 24 uur weer een waarschuwing")
    cap.records.clear(); state["payload"] = payload(mv=3500, age=8 * 3600); db.set_metadata(f"harepeater.lowbat.{F.PFX}", "0")
    await s5.refresh()
    check(not [m for _, m in cap.records if "batterij laag" in m], "oude meting (8 uur) geeft geen alarm")
    bot2, cap2 = make_bot(db, low_battery_notify="false"); db.set_metadata(f"harepeater.lowbat.{F.PFX}", "0")
    s7 = HARepeaterService(bot2); await s7.start(); s7._task.cancel(); state["payload"] = payload(mv=3500); await s7.refresh()
    check(not [m for _, m in cap2.records if "batterij laag" in m], "uitgezet op de kaart: geen waarschuwing")
    await s5.stop(); await s7.stop()

    # opschonen
    with db.connection() as c:
        c.execute("UPDATE repeater_telemetry SET recorded_at = ? WHERE id = 1", (int(time.time()) - 40 * 86400,)); c.commit()
    s5._retention_at = 0; s5._retention()
    with db.connection() as c: check(c.execute("SELECT COUNT(*) FROM repeater_telemetry WHERE id = 1").fetchone()[0] == 0, "rijen ouder dan keep_days worden opgeschoond")

    # current(): selectie op naam of sleutel
    check([r["prefix"] for r in s5.current("rptr")] == [F.PFX] and s5.current("bestaat-niet") == [] and [r["prefix"] for r in s5.current("a1b2")] == [F.PFX], "current(): zoeken op naam en sleutel")
    await runner.cleanup()
    print(f"\n{len(fails)} fouten"); sys.exit(1 if fails else 0)

asyncio.run(main())
