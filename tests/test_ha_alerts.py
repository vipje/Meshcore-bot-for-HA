"""HARepeater: waarschuwingen (herstart, offline, ruisvloer, airtime, buur weg), accu-geschiedenis en `rptr accu`."""
import asyncio, configparser, contextlib, logging, os, sqlite3, sys, tempfile, time, types
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
FIXTURES = str(_TESTS / "fixtures")
sys.path.insert(0, sys.argv[1]); os.chdir(sys.argv[1]); sys.path.insert(0, FIXTURES)
from aiohttp import web
import ha_states as F
from modules.service_plugins import ha_repeater_service as svc_mod
from modules.service_plugins.ha_repeater_service import HARepeaterService
from modules import ha_repeater_parser as P
from modules.i18n import Translator

def nl_translator():
    return Translator("nl", "translations/", "local/translations")

TR = nl_translator().translate

fails = []
def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c: fails.append(m)

class DB:
    def __init__(self, path): self.path = path; sqlite3.connect(path).execute("CREATE TABLE IF NOT EXISTS bot_metadata (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)").connection.commit()
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

state = {"payload": []}
async def handler(request): return web.json_response(state["payload"])

def states(n, uptime_min=18455.5, noise=-112, airtime=1.85, online="on", drop_neighbours=(), mv=3920):
    """Reading number n (own stats_key); the fixture states with a few values replaced."""
    now = time.time()
    out = []
    for e in F.repeater_states(now, f"2026-09-21T{8 + n // 6:02d}:{(n % 6) * 10:02d}:00", mv, 60) + F.room_states(now):
        eid = e["entity_id"]
        if eid.endswith("_uptime_" + F.SLUG): e["state"] = str(uptime_min)
        elif eid.endswith("_noise_floor_" + F.SLUG): e["state"] = str(noise)
        elif eid.endswith("_airtime_utilization_" + F.SLUG): e["state"] = str(airtime)
        elif "_online_" in eid and eid.startswith("binary_sensor"): e["state"] = online
        elif any(eid.endswith("neighbor_" + p) for p in drop_neighbours): continue
        out.append(e)
    return out

def warns(cap, word): return [m for lvl, m in cap.records if lvl == "WARNING" and f"HARepeater: {word}" in m]

async def make(db, **extra):
    cfg = configparser.ConfigParser()
    cfg["HARepeater"] = {"enabled": "true", "low_battery_notify": "false", **extra}
    log = logging.getLogger(f"al{time.time_ns()}"); cap = Capture(); log.addHandler(cap); log.setLevel(logging.DEBUG)
    s = HARepeaterService(types.SimpleNamespace(config=cfg, logger=log, db_manager=db, translator=nl_translator()))
    await s.start(); s._task.cancel()
    return s, cap

async def feed(s, n, **kw):
    state["payload"] = states(n, **kw); return await s.refresh()

async def main():
    app = web.Application(); app.router.add_get("/states", handler)
    runner = web.AppRunner(app); await runner.setup(); site = web.TCPSite(runner, "127.0.0.1", 0); await site.start()
    svc_mod.STATES_URL = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/states"
    os.environ["SUPERVISOR_TOKEN"] = "t"
    tmp = tempfile.mkdtemp()

    # ---- rustige situatie: geen enkele waarschuwing
    db = DB(f"{tmp}/a.db"); s, cap = await make(db)
    check(s.alert_reboot and s.alert_offline and s.alert_noise and s.alert_airtime and not s.alert_neighbors and s.noise_jump_db == 8 and s.airtime_max_pct == 10,
          "standaard: herstart, offline, ruis en airtime aan; buur-weg uit; 8 dB en 10 %")
    for n in range(1, 6): await feed(s, n, uptime_min=18455.5 + n * 10)
    check(not [m for l, m in cap.records if l == "WARNING"], "vijf rustige metingen: geen waarschuwing")

    # ---- herstart
    await feed(s, 6, uptime_min=3)
    w = warns(cap, "herstart"); print("   ", w)
    check(len(w) == 1 and "NL|XX|TOWN|RPTR|01" in w[0] and "was" in w[0], "uptime valt terug: waarschuwing 'herstart' met naam")
    await feed(s, 7, uptime_min=2)
    check(len(warns(cap, "herstart")) == 1, "en niet nog een keer binnen een uur")
    await feed(s, 8, uptime_min=13)
    check(len(warns(cap, "herstart")) == 1, "normaal doortellen na de herstart is geen nieuwe herstart")

    # ---- ruisvloer
    await feed(s, 9, uptime_min=23, noise=-108)
    check(not warns(cap, "ruisvloer"), "+4 dB is onder de grens van 8 dB")
    await feed(s, 10, uptime_min=33, noise=-98)
    w = warns(cap, "ruisvloer"); print("   ", w)
    check(len(w) == 1 and "-98" in w[0], "+14 dB t.o.v. de gewone waarde: waarschuwing 'ruisvloer hoog'")
    await feed(s, 11, uptime_min=43, noise=-95)
    check(len(warns(cap, "ruisvloer")) == 1, "maar één keer per dag")

    # ---- airtime
    await feed(s, 12, uptime_min=53, airtime=10)
    check(not warns(cap, "airtime"), "precies op de grens (10 %) is nog geen waarschuwing")
    await feed(s, 13, uptime_min=63, airtime=14.4)
    w = warns(cap, "airtime"); print("   ", w)
    check(len(w) == 1 and "14%" in w[0] and "10%" in w[0], "airtime boven de grens: waarschuwing met percentage en grens")
    await feed(s, 14, uptime_min=73, airtime=30)
    check(len(warns(cap, "airtime")) == 1, "maar één keer per dag")

    # ---- offline: twee leesrondes achter elkaar
    db2 = DB(f"{tmp}/b.db"); s2, cap2 = await make(db2)
    await feed(s2, 1); await feed(s2, 1, online="off")
    check(not warns(cap2, "offline"), "één ronde offline: nog niets (kan een haperende sensor zijn)")
    await feed(s2, 1, online="off")
    w = warns(cap2, "offline"); print("   ", w)
    check(len(w) == 1 and "NL|XX|TOWN|RPTR|01" in w[0], "twee rondes achter elkaar offline: waarschuwing")
    await feed(s2, 1, online="off"); await feed(s2, 1, online="off")
    check(len(warns(cap2, "offline")) == 1, "en niet steeds opnieuw")
    await feed(s2, 1, online="on"); await feed(s2, 1, online="off"); await feed(s2, 1, online="off")
    check(len(warns(cap2, "offline")) == 1, "na herstel en opnieuw uitvallen binnen een dag: nog steeds één")
    s2b, cap2b = await make(db2)
    await feed(s2b, 1, online="off"); await feed(s2b, 1, online="off")
    check(not warns(cap2b, "offline"), "ook na een herstart van de bot geen dubbele melding (staat in de database)")

    # ---- buur weg (staat standaard uit)
    db3 = DB(f"{tmp}/c.db"); s3, cap3 = await make(db3)
    for n in (1, 2, 3): await feed(s3, n)
    await feed(s3, 4, drop_neighbours=("984d7b",))
    check(not warns(cap3, "buur weg"), "uit op de kaart: geen melding als een buur verdwijnt")
    db4 = DB(f"{tmp}/d.db"); s4, cap4 = await make(db4, alert_neighbors="true")
    for n in (1, 2, 3): await feed(s4, n)
    await feed(s4, 4, drop_neighbours=("984d7b",))
    w = warns(cap4, "buur weg"); print("   ", w)
    check(len(w) == 1 and "NL-AB-RP02" in w[0], "aan: een buur die in de twee vorige metingen was en nu weg is, wordt met naam gemeld")
    db5 = DB(f"{tmp}/e.db"); s5, cap5 = await make(db5, alert_neighbors="true")
    await feed(s5, 1); await feed(s5, 2, drop_neighbours=("984d7b",))
    check(not warns(cap5, "buur weg"), "te weinig geschiedenis (2 metingen): geen melding")

    # ---- alles uit
    db6 = DB(f"{tmp}/f.db"); s6, cap6 = await make(db6, alert_reboot="false", alert_offline="false", alert_noise="false", alert_airtime="false", alert_neighbors="true")
    for n in range(1, 6): await feed(s6, n, uptime_min=18455.5 + n)
    await feed(s6, 6, uptime_min=1, noise=-80, airtime=50, online="off")
    await feed(s6, 7, uptime_min=2, noise=-80, airtime=50, online="off")
    check(not [m for l, m in cap6.records if l == "WARNING"], "alle schakelaars uit: nooit een waarschuwing")

    # ---- meldingsregel is herkenbaar voor de meldingsservice
    import re
    pat = re.compile(r"HARepeater: (batterij laag|herstart|offline|ruisvloer hoog|airtime hoog|buur weg)", re.I)
    check(all(pat.search(m) for m in [w0 for w0 in warns(cap, "herstart") + warns(cap, "ruisvloer") + warns(cap, "airtime") + warns(cap2, "offline") + warns(cap4, "buur weg")]), "alle waarschuwingsregels passen op het patroon van de meldingsservice")

    # ---- accu-geschiedenis
    hist = s.battery_history(F.KEY, 24)
    check(len(hist) == 14 and hist == sorted(hist) and hist[0][1] == 3920, "battery_history: alle opgeslagen metingen, oudste eerst")
    check(s.battery_history("onbekend", 24) == [], "onbekende repeater: leeg")
    with db.connection() as c: c.execute("UPDATE repeater_telemetry SET recorded_at = recorded_at - 259200"); c.commit()
    check(s.battery_history(F.KEY, 24) == [] and len(s.battery_history(F.KEY, 96)) == 14, "alleen metingen binnen de gevraagde periode")
    with db.connection() as c: c.execute("UPDATE repeater_telemetry SET recorded_at = recorded_at + 259200"); c.commit()

    # ---- parser: trend en tekst
    H = 3600
    t0 = 1_000_000
    flat = [(t0 + i * H, 3900) for i in range(0, 30)]
    falling = [(t0 + i * H, 3900 - i * 5) for i in range(0, 25)]        # 5 mV/u = 0,12 V/dag
    rising = [(t0 + i * H, 3800 + i * 4) for i in range(0, 25)]
    check(P.slope_per_day(flat) == 0.0 and abs(P.slope_per_day(falling) + 0.12) < 1e-9 and P.slope_per_day(rising) > 0, "slope_per_day: vlak, dalend (-0,12 V/dag) en stijgend")
    check(P.slope_per_day([(t0, 3900), (t0 + H, 3890), (t0 + 2 * H, 3880)]) is None and P.slope_per_day([(t0, 3900)]) is None, "trend onbekend bij minder dan 6 uur of 3 metingen")
    check(P.period_label(24, TR) == "24u" and P.period_label(47, TR) == "47u" and P.period_label(168, TR) == "7d", "periodetekst: uren tot 47, daarna dagen")
    t = P.battery_text("NL|RPTR", falling, 24, TR, 3600); print("   ", t)
    check(t.startswith("Accu NL|RPTR 24u: nu 3,78 V") and "min 3,78" in t and "max 3,90" in t and "-0,12 V/dag" in t and "laag over ~2 d" in t and "25 metingen" in t, "dalende accu: nu/min/max, trend en 'laag over ~N d'")
    check("stabiel" in P.battery_text("X", flat, 24, TR, 3600) and "laag over" not in P.battery_text("X", flat, 24, TR, 3600), "vlakke accu: 'stabiel'")
    t = P.battery_text("X", rising, 168, TR, 3600); print("   ", t)
    check("Accu X 7d" in t and "+0,10 V/dag" in t and "laag over" not in t, "stijgende accu (laden): +trend, geen voorspelling")
    check("nog maar 1 meting" in P.battery_text("X", [(t0, 3900)], 24, TR) and "nog maar 0 meting" in P.battery_text("X", [], 24, TR), "te weinig metingen: nette tekst")
    check(all(len(P.battery_text("NL|XX|TOWN|RPTR|01-LANGE-NAAM", r, 720, TR, 3600).encode()) <= 130 for r in (flat, falling, rising)), "past altijd in 130 bytes")
    far = [(t0 + i * H, 4100 - i // 4) for i in range(0, 25)]
    check("laag over" not in P.battery_text("X", far, 24, TR, 3600), "geen voorspelling als de accu pas over meer dan 60 dagen laag is")

    # ---- rptr accu (commando)
    import importlib
    from modules.commands.rptr_command import RptrCommand
    from modules.models import MeshMessage
    sent = []
    async def send_response(msg, text): sent.append(text); return True
    async def send_chunked(msg, texts): sent.extend(texts); return True
    cfg = configparser.ConfigParser(); cfg["Bot"] = {"bot_name": "T"}; cfg["Channels"] = {"monitor_channels": "#bot"}
    bot = types.SimpleNamespace(config=cfg, logger=logging.getLogger("cmd"), services={"harepeater": s}, translator=nl_translator(), command_manager=None)
    cmd = RptrCommand.__new__(RptrCommand)
    try:
        cmd = RptrCommand(bot)
    except Exception:
        pass
    cmd.send_response = send_response; cmd.send_response_chunked = send_chunked
    for text, expect in [("rptr accu", "Accu NL|XX|TOWN|RPTR|01 24u"), ("rptr accu 7d", "7d"), ("rptr batterij 12u", "12u"), ("rptr bat 3d", "3d")]:
        sent.clear(); await cmd.execute(MeshMessage(content=text, sender_id="V", is_dm=True)); print("   ", text, "->", sent)
        check(len(sent) == 1 and expect in sent[0] and sent[0].startswith("Accu"), f"'{text}' geeft de accu-regel ({expect})")
    sent.clear(); await cmd.execute(MeshMessage(content="rptr accu 999u", sender_id="V", is_dm=True))
    print("   ", sent)
    check(sent and "720" not in sent[0] and "30d" in sent[0], "periode wordt begrensd op 30 dagen")
    sent.clear(); await cmd.execute(MeshMessage(content="rptr accu bestaat-niet", sender_id="V", is_dm=True))
    check(sent and "geen repeater gevonden" in sent[0], "onbekende naam bij accu: nette melding")
    sent.clear(); await cmd.execute(MeshMessage(content="rptr", sender_id="V", is_dm=True))
    check(sent and sent[0].startswith("NL|XX|TOWN|RPTR|01") or (sent and "NL|LIM" in sent[0]), "gewone rptr werkt nog")
    for x in (s, s2, s2b, s3, s4, s5, s6): await x.stop()
    await runner.cleanup()
    print(f"\n{len(fails)} fouten"); sys.exit(1 if fails else 0)

asyncio.run(main())
