"""F1 service (reads, plans, posts, remembers, scores) and the f1 command, against the real patched upstream classes."""
import asyncio
import configparser
import contextlib
import json
import logging
import os
import pathlib as _pl
import sqlite3
import sys
import tempfile
import time
import types
from unittest.mock import MagicMock

_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")
FIXTURES = str(_TESTS / "fixtures")
TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
sys.path.insert(0, FIXTURES)
import f1_states as S


def import_with_stubs(fn):
    for _ in range(40):
        try:
            return fn()
        except ModuleNotFoundError as e:
            if e.name.split(".")[0] == "modules":
                raise
            sys.modules[e.name] = MagicMock()
            sys.modules.setdefault(e.name.split(".")[0], MagicMock())
    raise SystemExit("te veel ontbrekende modules")


def _imp():
    global MeshMessage, F1Command, F1Service, svc_mod, F, Translator
    from modules.models import MeshMessage
    from modules.commands.f1_command import F1Command
    from modules.service_plugins import f1_service as svc_mod
    from modules.service_plugins.f1_service import F1Service
    from modules import f1_data as F
    from modules.i18n import Translator


import_with_stubs(_imp)
svc_mod.GAP_BETWEEN_MESSAGES_S = 0


def nl_translator():
    return Translator("nl", "translations/", "local/translations")


TR = nl_translator().translate

fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


class DB:
    def __init__(self, path):
        self.path = path
        c = sqlite3.connect(path)
        c.execute("CREATE TABLE IF NOT EXISTS bot_metadata (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)")
        c.commit()
        c.close()

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        try:
            yield c
        finally:
            c.close()

    def get_metadata(self, k):
        with self.connection() as c:
            r = c.execute("SELECT value FROM bot_metadata WHERE key=?", (k,)).fetchone()
            return r[0] if r else None

    def set_metadata(self, k, v):
        with self.connection() as c:
            c.execute("INSERT OR REPLACE INTO bot_metadata (key, value) VALUES (?,?)", (k, v))
            c.commit()


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, r):
        self.records.append((r.levelname, r.getMessage()))


class Limiter:
    def __init__(self):
        import threading
        self.last_send = 123.0
        self._lock = threading.Lock()


def make_bot(db, extra=None, connected=True, send_ok=True):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "Own|🤖"}
    cfg["F1"] = {"enabled": "true", "channel": "#f1", **(extra or {})}
    make_bot.n = getattr(make_bot, "n", 0) + 1
    log = logging.getLogger(f"f1test{make_bot.n}")
    log.handlers = []
    cap = Capture()
    log.addHandler(cap)
    log.setLevel(logging.DEBUG)
    sent = []

    async def send_channel_message(channel, text, skip_user_rate_limit=False):
        if not send_ok["v"]:
            return False
        sent.append((channel, text))
        bot.rate_limiter.last_send = time.monotonic()      # like upstream: every send notes itself
        return True

    bot = types.SimpleNamespace(config=cfg, logger=log, db_manager=db, connected=connected, rate_limiter=Limiter(), services={},
                                command_manager=types.SimpleNamespace(send_channel_message=send_channel_message, monitor_channels=["#bot", "#test"]),
                                translator=nl_translator())
    return bot, cap, sent


async def main():
    tmp = tempfile.mkdtemp()
    db = DB(f"{tmp}/bot.db")
    ok_send = {"v": True}
    bot, cap, sent = make_bot(db, send_ok=ok_send)
    svc = F1Service(bot)
    bot.services["f1"] = svc
    svc.game = None
    from modules.f1_game import F1Game
    svc.game = F1Game(db)
    svc.game.ensure_tables()

    check(svc.channel == "#f1" and svc.cfg["daily_time"] == "12:00" and svc.cfg["live_milestones"] == [25, 50, 75] and svc.live_read == 30 and svc.game_enabled, "instellingen uit de sectie [F1] gelezen")

    # a race weekend: predictions first, then the result
    A, B, C = "aa" * 32, "bb" * 32, "cc" * 32
    svc.game.predict("2026", "16", A, "Alice", "NOR", 1.0, None, {"NOR", "VER"}, TR)
    svc.game.predict("2026", "16", B, "Bob", "VER", 1.0, None, {"NOR", "VER"}, TR)
    svc.game.predict("2026", "16", C, "Cor", "LEC", 1.0, None, {"NOR", "VER", "LEC"}, TR)

    t_daily = S.ts(2026, 9, 21, 10)
    await svc.process(S.states(t_daily), t_daily)
    check(sent == [("#f1", sent[0][1])] and sent[0][1].startswith("F1: nog 13 dagen tot de GP Italië (Monza)"), "eerste ronde: het aftelbericht van vandaag, in kanaal #f1")
    check(bot.rate_limiter.last_send == 123.0, "een F1-bericht gebruikt het antwoordbudget van de bot niet op")
    n = len(sent)
    await svc.process(S.states(t_daily + 300), t_daily + 300)
    check(len(sent) == n, "vijf minuten later niets opnieuw")
    raw = db.get_metadata("f1.state")
    check(raw and "daily:2026-09-21" in json.loads(raw)["posted"], "wat is gepost staat in de database")
    bot2, cap2, sent2 = make_bot(db, send_ok={"v": True})
    svc2 = F1Service(bot2)
    svc2.game = svc.game
    svc2._load_state()
    await svc2.process(S.states(t_daily + 600), t_daily + 600)
    check(sent2 == [], "na een herstart (nieuwe service, zelfde database) wordt niets herhaald")
    check(any("F1: gevonden: volgende race Italian Grand Prix (ronde 16)" in m and "laatste uitslag ronde 15" in m for _l, m in cap2.records), "de eerste ronde logt wat er gevonden is (ook de live-sensoren)")

    sent.clear()
    t_res = S.ts(2026, 10, 4, 15, 0)
    st = S.states(t_res, race_done=True, next_is_this=True, standings_updated=False)
    await svc.process(st, t_res)
    texts = [m for _c, m in sent]
    print("   ", texts)
    check(texts[0].startswith("Uitslag GP Italië (Monza): 1 NOR, 2 VER, 3 LEC") and texts[1].startswith("Winnaar GP Italië (Monza): Nor NORson (McLaren)"), "uitslag en winnaar in het kanaal")
    game = [m for m in texts if m.startswith("Spel:")]
    check(len(game) == 1 and "3 deelnemers" in game[0] and "Alice (5 pt)" in game[0] and "Bob (2 pt)" in game[0] and "Cor (2 pt)" in game[0] and "Stand: 1 Alice 5" in game[0], "spelbericht: wie goed had, en de stand")
    check(not any(m.startswith("WK na") for m in texts), "klassement wacht tot het bij deze race hoort")
    sent.clear()
    t_st = S.ts(2026, 10, 4, 15, 30)
    await svc.process(S.states(t_st, race_done=True, standings_updated=True), t_st)
    check(len(sent) == 2 and sent[0][1].startswith("WK na GP Italië (Monza): 1 NOR") and sent[1][1].startswith("Constructeurs: 1 McLaren"), "een half uur later: het klassement")
    sent.clear()
    await svc.process(S.states(t_st + 300, race_done=True, standings_updated=True), t_st + 300)
    check(sent == [] and svc.game.points_of("2026", A) == (5, 1), "niets dubbel gepost en de punten zijn niet dubbel geteld")

    # failing send: not marked, backed off, one warning
    ok_send["v"] = False
    cap.records.clear()
    t2 = S.ts(2026, 9, 22, 10)
    await svc.process(S.states(t2), t2)
    check(not any(k.startswith("daily:2026-09-22") for k in svc.st["posted"]), "mislukt versturen: het bericht is niet als gepost gemarkeerd")
    n_log = len([1 for l, m in cap.records if "versturen naar #f1 mislukt" in m])
    await svc.process(S.states(t2 + 60), t2 + 60)
    await svc.process(S.states(t2 + 120), t2 + 120)
    check(n_log == 1 and len([1 for l, m in cap.records if "versturen naar #f1 mislukt" in m]) == 1, "één waarschuwing, en de service probeert het niet elke minuut opnieuw")
    ok_send["v"] = True
    sent.clear()
    await svc.process(S.states(t2 + 1000), t2 + 1000)
    check(len(sent) == 1 and sent[0][1].startswith("F1: nog 12 dagen"), "na de wachttijd lukt het weer en het bericht komt alsnog")

    # not connected to the radio
    bot3, _c3, sent3 = make_bot(DB(f"{tmp}/b3.db"), connected=False)
    svc3 = F1Service(bot3)
    await svc3.process(S.states(t_daily), t_daily)
    check(sent3 == [] and svc3.st["posted"] == [], "radio niet verbonden: niets verstuurd en niets gemarkeerd")

    # reading intervals
    svc.snapshot = F.parse(S.states(S.ts(2026, 9, 21, 10)))
    real = time.time
    time.time = lambda: S.ts(2026, 9, 21, 10)
    check(svc._delay() == 300, "ver van een sessie: elke 5 minuten lezen")
    time.time = lambda: S.ts(2026, 10, 3, 13, 0)
    check(svc._delay() == 60, "binnen 90 minuten voor een sessie: elke minuut")
    svc.snapshot = F.parse(S.states(S.ts(2026, 10, 4, 13, 30), live_states=S.live("Race", "live", 5)))
    check(svc._delay() == 30, "tijdens een sessie: elke 30 seconden (instelling)")
    time.time = real
    svc.snapshot = F.parse(S.states(S.ts(2026, 9, 21, 10)))
    check(svc.lock_ts() == S.ts(2026, 10, 3, 14) and svc.valid_codes() == {"VER", "NOR", "LEC", "PIA", "HAM", "RUS", "SAI", "ALO", "GAS", "TSU"}, "sluitingstijd (kwalificatie) en geldige coureurcodes")

    # ------------------------------------------------------------- the command
    async def run(text, is_dm=False, pubkey=None, name="Alex", service=svc, channel="#f1"):
        b = types.SimpleNamespace(config=configparser.ConfigParser(), logger=logging.getLogger("c"), services=({"f1": service} if service else {}),
                                  command_manager=types.SimpleNamespace(monitor_channels=["#bot", "#test"]), translator=nl_translator())
        cmd = F1Command(b)
        out = []

        async def send_response(message, content, **kw):
            out.append(content)
            return True

        async def send_response_chunked(message, chunks, **kw):
            out.extend(chunks)
            return True
        cmd.send_response, cmd.send_response_chunked = send_response, send_response_chunked
        await cmd.execute(MeshMessage(content=text, sender_id=name, sender_pubkey=pubkey, is_dm=is_dm, channel=None if is_dm else channel))
        return out

    svc.snapshot = F.parse(S.states(S.ts(2026, 9, 21, 10)))
    svc.last_read = 1.0
    r = await run("f1")
    check(len(r) == 1 and r[0].startswith("Volgende: GP Italië (Monza), zo 4 okt 15:00 (over "), "f1: volgende race")
    r = await run("!f1 stand")
    check(len(r) == 2 and r[0].startswith("WK na ronde 15: 1 VER 288 | 2 NOR 276") and all(len(x.encode()) <= 130 for x in r) and "10 TSU" in r[1], "f1 stand: top 10 met de ronde, in twee berichten")
    r = await run("f1 wk")
    check(r[0].startswith("WK na ronde 15"), "f1 wk is hetzelfde")
    r = await run("f1 team")
    check(r[0].startswith("Constructeurs: 1 McLaren 460 | 2 Ferrari 420"), "f1 team")
    r = await run("f1 uitslag")
    check(len(r) == 2 and r[0].startswith("Uitslag GP Singapore: 1 VER, 2 NOR") and r[1].startswith("Winnaar GP Singapore"), "f1 uitslag: top 10 en winnaar")
    r = await run("f1 nu")
    check(r[0] == "Geen F1-sessie bezig." and r[1].startswith("Volgende:"), "f1 nu buiten een sessie")
    svc.snapshot = F.parse(S.states(S.ts(2026, 10, 4, 13, 30), live_states=S.live("Race", "live", 14)))
    r = await run("f1 nu")
    check(len(r) == 1 and r[0].startswith("Race bezig | Ronde 14/53: 1 VER | 2 NOR +3,400"), "f1 nu tijdens de race")
    svc.snapshot = F.parse(S.states(S.ts(2026, 9, 21, 10)))
    r = await run("f1 onzin")
    check(r[0].startswith("F1: gebruik f1"), "onbekend onderdeel: uitleg")
    r = await run("f1", service=None)
    check("staat uit" in r[0], "service niet geladen: uitleg")
    svc.last_read = 0.0
    r = await run("f1")
    check("nog geen gegevens" in r[0], "nog niet gelezen: melding")
    svc.last_read = 1.0

    # the game through the command
    D = "dd" * 32
    r = await run("f1 voorspel VER", is_dm=False, pubkey=None, name="Dirk")
    check("alleen via een DM" in r[0] and svc.game.pick_of("2026", "16", D) is None, "voorspellen in het kanaal wordt geweigerd met uitleg (geen sleutel = geen stem)")
    r = await run("f1 voorspel VER", is_dm=True, pubkey=D, name="Dirk")
    check(r == ["Genoteerd: je voorspelt VER als winnaar."] and svc.game.pick_of("2026", "16", D) == "VER", "per DM: genoteerd op de sleutel")
    r = await run("f1 voorspel nor", is_dm=True, pubkey=D, name="Dirk")
    check(r[0].startswith("Aangepast: je voorspelt nu NOR (was VER)"), "per DM: aanpassen")
    r = await run("f1 voorspel XXX", is_dm=True, pubkey=D, name="Dirk")
    check("ken ik niet" in r[0] and svc.game.pick_of("2026", "16", D) == "NOR", "onbekende code")
    r = await run("f1 voorspel", is_dm=True, pubkey=D, name="Dirk")
    check(r[0].startswith("Wie wint de GP Italië (Monza)? f1 voorspel <code>, bv. "), "zonder code: uitleg met voorbeelden")
    r = await run("f1 voorspel VER", is_dm=True, pubkey=None, name="Onbekend")
    check("sleutel" in r[0], "DM zonder bekende sleutel: geweigerd")
    past = {"quali": S.ts(2026, 9, 19, 14), "race": S.ts(2026, 9, 20, 13)}
    svc.snapshot["next"] = dict(svc.snapshot["next"], sessions=past)
    r = await run("f1 voorspel VER", is_dm=True, pubkey="ee" * 32, name="Eve")
    check("gesloten" in r[0] and svc.game.pick_of("2026", "16", "ee" * 32) is None, "na de start van de kwalificatie: gesloten")
    svc.snapshot = F.parse(S.states(S.ts(2026, 9, 21, 10)))
    r = await run("f1 spel")
    print("   ", r)
    check(r[0].startswith("Spel 2026: Stand: 1 Alice 5 | 2 Bob 2 | 3 Cor 2") and any("Meedoen: DM mij f1 voorspel <code> (GP Italië (Monza))" in x for x in r), "f1 spel in het kanaal: stand en hoe je meedoet")
    r = await run("f1 spel", is_dm=True, pubkey=A, name="Alice")
    check("Jij: 5 pt in 1 races" in " ".join(r), "f1 spel per DM: je eigen punten")
    r = await run("f1 spel", is_dm=True, pubkey=D, name="Dirk")
    check("Jij: 0 pt in 0 races, je voorspelt NOR" in " ".join(r), "en je eigen voorspelling")
    svc.game_enabled = False
    r = await run("f1 voorspel VER", is_dm=True, pubkey=D)
    check("staat uit" in r[0], "spel uitgezet: melding")
    svc.game_enabled = True
    # channel rule: only the f1 command gets #f1 (its own channel list), no other command
    cmd = F1Command(types.SimpleNamespace(config=configparser.ConfigParser(), logger=logging.getLogger("c"), services={},
                                          command_manager=types.SimpleNamespace(monitor_channels=["#bot", "#test"]), translator=nl_translator()))
    check(cmd.get_config_value("F1_Command", "enabled", fallback=True, value_type="bool") is True and cmd.matches_keyword(MeshMessage(content="F1 stand", sender_id="x", is_dm=True)), "trefwoord f1, hoofdletters maken niet uit")
    check(not cmd.matches_keyword(MeshMessage(content="f1x", sender_id="x", is_dm=True)) and not cmd.matches_keyword(MeshMessage(content="formule f1", sender_id="x", is_dm=True)), "'f1x' of 'formule f1' matcht niet")

    # the radio has '#F1' (another key than '#f1'): never post there
    botc, capc, sentc = make_bot(db, extra={"channel": "#F1"}, send_ok={"v": True})
    botc.channel_manager = types.SimpleNamespace(get_channel_by_name=lambda n: {"channel_name": "#F1", "channel_idx": 6})
    svcc = F1Service(botc)
    check(svcc.channel == "#f1", "een hashtagkanaal op de kaart wordt in kleine letters gezet")
    check(await svcc._send("test") is False and sentc == [] and any("hoofdletter" in m for _l, m in capc.records), "kanaal op de radio met hoofdletter: niets gepost, duidelijke melding")
    botc.channel_manager = types.SimpleNamespace(get_channel_by_name=lambda n: {"channel_name": "#f1", "channel_idx": 6})
    check(await svcc._send("test") is True and sentc == [("#f1", "test")], "kanaal '#f1' zoals anderen het hebben: gewoon posten")

    print(f"\n{len(fails)} fouten")
    sys.exit(1 if fails else 0)


asyncio.run(main())
