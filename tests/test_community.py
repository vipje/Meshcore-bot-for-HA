"""Community commands and games (2.14.0) against the real patched upstream classes:
topu without bots, dx (DX Jacht), pad, sig, meshkaart, karma, checkin, prikbord, noodnummers, weetje, peiling,
herinner + Reminders service, voorspel, buien, xp + badge (Mesh RPG), the archive and the Community service."""
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
from datetime import datetime
from unittest.mock import MagicMock

_TESTS = _pl.Path(__file__).resolve().parent
TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.WARNING)


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
    global MeshMessage, Translator, MC, MA, C
    from modules.models import MeshMessage
    from modules.i18n import Translator
    from modules import mesh_community as MC, mesh_archive as MA
    C = types.SimpleNamespace()
    from modules.commands.topusers_command import TopUsersCommand
    from modules.commands.dx_command import DxCommand
    from modules.commands.pad_command import PadCommand, short_names, node_ids_of
    from modules.commands.sig_command import SigCommand
    from modules.commands.meshkaart_command import MeshkaartCommand
    from modules.commands.karma_command import KarmaCommand
    from modules.commands.checkin_command import CheckinCommand
    from modules.commands.prikbord_command import PrikbordCommand
    from modules.commands.noodnummers_command import NoodnummersCommand
    from modules.commands.aed_command import AedCommand
    from modules.commands.kenteken_command import KentekenCommand
    from modules.commands.weetje_command import WeetjeCommand
    from modules.commands.peiling_command import PeilingCommand, parse_poll
    from modules.commands.herinner_command import HerinnerCommand
    from modules.commands.voorspel_command import VoorspelCommand
    from modules.commands.buien_command import BuienCommand, parse_raintext, timeline
    from modules.commands.xp_command import XpCommand
    from modules.commands.badge_command import BadgeCommand
    from modules.service_plugins.reminders_service import RemindersService
    from modules.service_plugins.community_service import CommunityService
    for k, v in list(locals().items()):
        setattr(C, k, v)


import_with_stubs(_imp)

fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


class DB:
    def __init__(self, path):
        self.path = path
        with self.connection() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)")
            c.execute("CREATE TABLE message_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER NOT NULL, sender_id TEXT NOT NULL, channel TEXT, content TEXT NOT NULL, is_dm BOOLEAN NOT NULL, hops INTEGER, snr REAL, rssi INTEGER, path TEXT)")
            c.execute("CREATE TABLE command_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER NOT NULL, sender_id TEXT NOT NULL, command_name TEXT NOT NULL, channel TEXT, is_dm BOOLEAN NOT NULL, response_sent BOOLEAN NOT NULL)")
            c.execute("CREATE TABLE path_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER NOT NULL, sender_id TEXT NOT NULL, channel TEXT, path_length INTEGER NOT NULL, path_string TEXT NOT NULL, hops INTEGER)")
            c.execute("CREATE TABLE complete_contact_tracking (id INTEGER PRIMARY KEY AUTOINCREMENT, public_key TEXT NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL, last_heard TIMESTAMP DEFAULT CURRENT_TIMESTAMP, latitude REAL, longitude REAL, last_advert_timestamp TIMESTAMP)")
            c.commit()

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


OWN = "Mesh|HA|🤖"


def make_bot(db, sections=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": OWN, "bot_latitude": "51.25", "bot_longitude": "5.70", "timezone": "Europe/Amsterdam"}
    for name, values in (sections or {}).items():
        cfg[name] = values
    bot = types.SimpleNamespace(config=cfg, logger=logging.getLogger("community"), db_manager=db, services={},
                                translator=Translator("nl", "translations/", "local/translations"), connected=True)
    bot.command_manager = types.SimpleNamespace(monitor_channels=["#bot", "#test"], commands={})
    return bot


def wire(cmd):
    out = []

    async def send_response(message, content, **kw):
        out.append(content)
        return True

    async def send_response_chunked(message, chunks, **kw):
        out.extend(chunks)
        return True
    cmd.send_response, cmd.send_response_chunked = send_response, send_response_chunked
    cmd.get_max_message_length = lambda message: 130
    return out


async def run(cmd, text, name="Piet", is_dm=False, pubkey=None, channel="#test", **extra):
    out = wire(cmd)
    msg = MeshMessage(content=text, sender_id=name, sender_pubkey=pubkey, is_dm=is_dm, channel=None if is_dm else channel, **extra)
    if cmd.can_execute(msg):
        await cmd.execute(msg)
    return out


def TR_NL(key, **kw):
    return Translator("nl", "translations/", "local/translations").translate(key, **kw)


def fits(texts):
    return all(len(t.encode("utf-8")) <= 130 for t in texts)


async def main():
    tmp = tempfile.mkdtemp()
    db = DB(f"{tmp}/bot.db")
    bot = make_bot(db)
    now = int(time.time())

    with db.connection() as c:
        for i in range(12):
            c.execute("INSERT INTO message_stats (timestamp, sender_id, channel, content, is_dm) VALUES (?,?,?,?,0)", (now - 60 - i, "BE-ExampleNode-BOT", "#test", "t"))
        for i in range(8):
            c.execute("INSERT INTO message_stats (timestamp, sender_id, channel, content, is_dm) VALUES (?,?,?,?,0)", (now - 60 - i, "Piet", "#test", "hoi"))
        for i in range(5):
            c.execute("INSERT INTO message_stats (timestamp, sender_id, channel, content, is_dm) VALUES (?,?,?,?,0)", (now - 60 - i, "Klaas", "#test", "hoi"))
        for i in range(3):
            c.execute("INSERT INTO message_stats (timestamp, sender_id, channel, content, is_dm) VALUES (?,?,?,?,0)", (now - 60 - i, OWN, "#test", "x"))
        c.execute("INSERT INTO message_stats (timestamp, sender_id, channel, content, is_dm) VALUES (?,?,?,?,0)", (now - 60, "🤖Helper", "#test", "x"))
        c.execute("INSERT INTO message_stats (timestamp, sender_id, channel, content, is_dm) VALUES (?,?,?,?,0)", (now - 60, "Anna", "#test", "x"))
        c.commit()

    # ------------------------------------------------------------------ topu
    r = await run(C.TopUsersCommand(bot), "topu")
    check(len(r) == 1 and r[0].startswith("Top users") and "Piet: 8" in r[0] and "Klaas: 5" in r[0] and "Anna: 1" in r[0], "topu toont de mensen")
    check("BOT" not in r[0] and "Helper" not in r[0] and OWN not in r[0], "topu laat andere bots en de bot zelf weg (standaard)")
    bot_off = make_bot(db, {"Topusers_Command": {"hide_bots": "false"}})
    r = await run(C.TopUsersCommand(bot_off), "topu")
    check("BE-ExampleNode-BOT: 12" in r[0], "topu met 'bots weglaten' uit toont ze wel (schakelaar werkt)")
    bot_ex = make_bot(db, {"Topusers_Command": {"exclude": "Klaas"}})
    r = await run(C.TopUsersCommand(bot_ex), "topu")
    check("Klaas" not in r[0] and "Piet: 8" in r[0] and "BOT" not in r[0], "de handmatige uitsluitlijst werkt nog, samen met het weglaten van bots")
    check(any(f["key"] == "hide_bots" and f["default"] is True for f in C.TopUsersCommand.settings_schema), "topu-kaart heeft de schakelaar 'Leave out bots', standaard aan")

    # ------------------------------------------------------------------ helpers
    t0 = datetime(2026, 9, 23, 17, 0).timestamp()
    at = MC.parse_when("18:30", bot, t0)
    check(MC.local_now(bot, at).strftime("%d %H:%M") == "23 18:30", "parse_when 18:30 = vandaag")
    at = MC.parse_when("16:00", bot, t0)
    check(MC.local_now(bot, at).strftime("%d %H:%M") == "24 16:00", "parse_when 16:00 (al voorbij) = morgen")
    check(MC.parse_when("30m", bot, t0) == int(t0) + 1800 and MC.parse_when("2u", bot, t0) == int(t0) + 7200 and MC.parse_when("1d", bot, t0) == int(t0) + 86400, "parse_when 30m, 2u, 1d")
    check(MC.parse_when("morgen", bot, t0) is None and MC.parse_when("25:00", bot, t0) is None, "parse_when weigert onzin")
    from datetime import date
    check(MC.streaks(["2026-09-20", "2026-09-21", "2026-09-22"], date(2026, 9, 23)) == (3, 3), "reeks loopt door als gisteren de laatste dag was")
    check(MC.streaks(["2026-09-18", "2026-09-19", "2026-09-22", "2026-09-23"], date(2026, 9, 23)) == (2, 2), "een gemiste dag begint de reeks opnieuw")
    check(MC.streaks(["2026-09-20"], date(2026, 9, 23)) == (0, 1), "reeks is 0 na twee dagen niets")
    check(MC.pack_lines("H:", ["a" * 60, "b" * 60, "c" * 60], 130) == ["H: " + "a" * 60 + " | " + "b" * 60, "c" * 60], "pack_lines verdeelt over berichten")
    check(MC.is_bot_name(bot, "BE-ExampleNode-BOT") and MC.is_bot_name(bot, OWN) and MC.is_bot_name(bot, "🤖Helper") and not MC.is_bot_name(bot, "Piet"), "bots herkennen zoals de Bots-pagina")

    # ------------------------------------------------------------------ archive + dx
    day = 86400
    with db.connection() as c:
        rows = [(now - 120, "Piet", 3, "aa,bb,cc"), (now - 100, "Piet", 5, "aa,bb,cc,dd,ee"), (now - 90, "Klaas", 4, "aa,bb,cc,dd"),
                (now - 80, "BE-ExampleNode-BOT", 9, "1,2,3,4,5,6,7,8,9"), (now - 3 * day, "Anna", 2, "aa,bb")]
        for ts, n, h, p in rows:
            c.execute("INSERT INTO path_stats (timestamp, sender_id, channel, path_length, path_string, hops) VALUES (?,?,?,?,?,?)", (ts, n, "#test", h, p, h))
        for i in range(4):
            c.execute("INSERT INTO command_stats (timestamp, sender_id, command_name, channel, is_dm, response_sent) VALUES (?,?,?,?,0,1)", (now - 50, "Piet", "ping", "#test"))
        c.commit()
    check(MA.sync(bot, now, force=True), "archief bijwerken")
    with db.connection() as c:
        act = dict(((n, (m, k)) for n, d, m, k in c.execute("SELECT name, day, messages, commands FROM community_activity")))
        dxr = {n: h for n, h in c.execute("SELECT name, MAX(hops) FROM community_dx GROUP BY name")}
    check(act.get("Piet") == (8, 4) and act.get("Klaas") == (5, 0), "archief: berichten en commando's per persoon per dag")
    check(dxr.get("Piet") == 5 and dxr.get("Klaas") == 4, "archief: beste hops per persoon per dag")
    # upstream clears its stats after 7 days: the archive keeps what it had
    with db.connection() as c:
        c.execute("DELETE FROM message_stats WHERE sender_id='Piet'")
        c.execute("DELETE FROM path_stats WHERE sender_id='Piet'")
        c.commit()
    MA.sync(bot, now + 5, force=True)
    with db.connection() as c:
        m = c.execute("SELECT messages FROM community_activity WHERE name='Piet'").fetchone()[0]
        h = c.execute("SELECT hops FROM community_dx WHERE name='Piet'").fetchone()[0]
    check(m == 8 and h == 5, "als upstream oude statistieken weggooit, blijft het archief staan")
    check(not MA.sync(bot, now + 10), "archief bijwerken hooguit eens per minuut (tenzij geforceerd)")
    # old archived day beyond 7 days still counts 'ever'
    with db.connection() as c:
        c.execute("INSERT INTO community_dx (name, day, hops, ts, path) VALUES ('Oude Jan', '2025-01-05', 8, ?, 'x')", (int(datetime(2025, 1, 5, 12, 0).timestamp()),))
        c.commit()

    dx = C.DxCommand(bot)
    r = await run(dx, "dx")
    check(len(r) == 1 and r[0].startswith("DX Jacht: week Piet 5 hops") and "ooit Oude Jan 8 hops (05-01)" in r[0] and fits(r), f"dx: records week/maand/ooit, bot overgeslagen: {r}")
    r = await run(dx, "dx top")
    check(r and r[0].startswith("DX top (week): 1. Piet 5 | 2. Klaas 4") and "BOT" not in r[0], "dx top: ranglijst zonder bots")
    r = await run(dx, "dx top ooit")
    check(r[0].startswith("DX top (ooit): 1. Oude Jan 8 | 2. Piet 5"), "dx top ooit")
    r = await run(dx, "dx ik", name="Klaas")
    check(r == ["DX Klaas: week 4 | maand 4 | ooit 4"], f"dx ik: {r}")
    r = await run(dx, "dx Niemand")
    check(r == ["DX Niemand: nog geen bericht via repeaters gezien."], "dx <onbekend>")

    # ------------------------------------------------------------------ pad
    check(C.node_ids_of(MeshMessage(content="x", path="4a,c2,8c (3 hops)")) == ["4A", "C2", "8C"], "pad: route uit de padtekst")
    check(C.node_ids_of(MeshMessage(content="x", routing_info={"path_length": 0})) == [], "pad: direct")
    check(C.node_ids_of(MeshMessage(content="x", routing_info={"path_length": 2, "path_nodes": ["ab12", "cd34"]})) == ["AB12", "CD34"], "pad: routing_info (2-byte hops)")
    check(C.node_ids_of(MeshMessage(content="x")) is None, "pad: geen route bekend")
    names = [("Horsthausen", False), ("YAGI-Noord", True), ("Westerkappeln", False), ("Westdorf", True)]
    check(C.short_names(names, 60) == "Horsthausen→YAGI-Noord?→Westerkappeln→Westdorf?", "pad: volle namen als het past")
    short = C.short_names(names, 40)
    check(len(short.encode()) <= 40 and short.count("→") == 3 and "?" in short, f"pad: namen korter tot het past ({short})")

    class FakePath:
        async def _lookup_repeater_names(self, ids):
            return {"4A": {"found": True, "name": "Horsthausen", "latitude": 51.5, "longitude": 5.9},
                    "C2": {"found": True, "name": "YAGI", "latitude": 51.7, "longitude": 6.2, "geographic_guess": True, "confidence": 0.6},
                    "8C": {"found": True, "collision": True, "matches": 2}}
    with db.connection() as c:
        c.execute("INSERT INTO complete_contact_tracking (public_key, name, role, latitude, longitude) VALUES ('ff'||hex(randomblob(31)), 'Piet', 'companion', 51.40, 5.80)")
        c.commit()
    bot.command_manager.commands["path"] = FakePath()
    pad = C.PadCommand(bot)
    r = await run(pad, "pad", path="4a,c2,8c (3 hops)", hops=3)
    check(len(r) == 1 and r[0].startswith("3 hops · ") and "hemelsbreed" in r[0] and "Horsthausen→YAGI?→8c?" in r[0] and fits(r), f"pad: hops, afstand hemelsbreed (niet alle posities bekend), namen, ? bij gok/dubbel: {r}")

    class FakePath2:
        async def _lookup_repeater_names(self, ids):
            return {"4A": {"found": True, "name": "Horsthausen", "latitude": 51.5, "longitude": 5.9}}
    bot.command_manager.commands["path"] = FakePath2()
    r = await run(pad, "pad", path="4a (1 hops)", hops=1)
    check(r[0].startswith("1 hop · ") and " km · Horsthausen" in r[0] and "hemelsbreed" not in r[0], f"pad: alle posities bekend = afstand langs de route: {r}")
    r = await run(pad, "pad", routing_info={"path_length": 0}, hops=0)
    check(r == ["Direct ontvangen, zonder repeaters (0 hops)."], "pad: direct")

    # ------------------------------------------------------------------ sig
    sig = C.SigCommand(bot)
    r = await run(sig, "sig", snr=7.5, rssi=-97, hops=3, path="4a,c2,8c (3 hops)")
    check(r == ["Signaal: SNR 7,5 dB, RSSI -97 dBm, 3 hops (laatste repeater naar de bot): goed"], f"sig met hops: {r}")
    r = await run(sig, "sig", snr=-7.25, rssi=-124, hops=0, routing_info={"path_length": 0})
    check(r == ["Signaal: SNR -7,2 dB, RSSI -124 dBm, direct (jouw antenne): zwak"], f"sig direct, zwak: {r}")
    r = await run(sig, "sig", snr=-12.0, rssi=-130, hops=1)
    check(r and r[0].endswith("heel zwak, op de grens"), "sig heel zwak")
    r = await run(sig, "sig")
    check(r == ["Geen signaalgegevens bij dit bericht."], "sig zonder gegevens")

    # ------------------------------------------------------------------ meshkaart
    with db.connection() as c:
        c.execute("INSERT INTO complete_contact_tracking (public_key, name, role, latitude, longitude) VALUES ('r1', 'Rep1', 'repeater', 51.1, 5.1)")
        c.execute("INSERT INTO complete_contact_tracking (public_key, name, role) VALUES ('rs1', 'Room1', 'roomserver')")
        c.execute("INSERT INTO complete_contact_tracking (public_key, name, role, last_heard) VALUES ('old', 'Oud', 'companion', datetime('now','-3 days'))")
        c.execute("INSERT INTO complete_contact_tracking (public_key, name, role, last_heard) VALUES ('older', 'Ouder', 'companion', datetime('now','-30 days'))")
        c.commit()
    r = await run(C.MeshkaartCommand(bot), "meshkaart")
    check(r == ["Mesh 24u: 3 nodes (1 companions, 1 repeaters, 1 rooms), 2 met positie | 7d: 4 | ooit: 5"], f"meshkaart telt per rol en venster: {r}")

    # ------------------------------------------------------------------ karma
    karma = C.KarmaCommand(bot)
    r = await run(karma, "karma Klaas", name="Piet")
    check(r == ["+1 karma voor Klaas van Piet (totaal 1)"], f"karma geven: {r}")
    r = await run(karma, "karma klaas", name="Piet")
    check(r == ["Klaas kreeg vandaag al karma van jou."], "karma: één keer per dag aan dezelfde")
    r = await run(karma, "karma Piet", name="Piet")
    check(r == ["Jezelf karma geven telt niet."], "karma: niet aan jezelf")
    r = await run(karma, "karma BE-ExampleNode-BOT", name="Piet")
    check(r == ["Bots krijgen geen karma."], "karma: niet aan bots")
    r = await run(karma, "karma Niemand", name="Piet")
    check(r and r[0].startswith("Niemand niet gezien in de laatste 30 dagen"), "karma: alleen aan namen die de bot kent")
    r = await run(karma, "karma Piet", name="Klaas")      # Piet's raw stats are gone, but the archive knows him
    check(r == ["+1 karma voor Piet van Klaas (totaal 1)"], "karma: naam ook bekend uit het archief (upstream bewaart maar 7 dagen)")
    bot_k = make_bot(db, {"Karma_Command": {"per_day": "1"}})
    r = await run(C.KarmaCommand(bot_k), "karma Anna", name="Piet")
    check(r == ["Je hebt vandaag al 1 karma gegeven. Morgen weer."], "karma: dagelijks maximum (instelling per_day)")
    r = await run(karma, "karma", name="Klaas")
    check(r == ["Klaas: 1 karma"], "karma: eigen punten")
    r = await run(karma, "topkarma")
    check(r and r[0].startswith("Karma top: 1. ") and "Klaas 1" in r[0] and "Piet 1" in r[0], f"topkarma: {r}")

    # ------------------------------------------------------------------ checkin
    ck = C.CheckinCommand(bot)
    base = datetime(2026, 9, 20, 9, 0).timestamp()
    for d in range(3):
        text = ck.check_in("Piet", base + d * day)
    check(text == "Ingecheckt, Piet! Reeks 3 d (record 3), vandaag 1 ingecheckt.", f"checkin: reeks van 3 dagen: {text}")
    check(ck.check_in("Piet", base + 2 * day + 3600).startswith("Piet, je was vandaag al ingecheckt. Reeks 3 d"), "checkin: twee keer op een dag telt niet dubbel")
    ck.check_in("Klaas", base + 2 * day)
    top = ck.top(130, base + 2 * day)
    check(top == ["Langste reeks: 1. Piet 3 | 2. Klaas 1"], f"checkin top: {top}")
    late = datetime(2026, 9, 23, 0, 30).timestamp()      # half past midnight local time: already the new day
    check(MC.local_day(bot, late).isoformat() == "2026-09-23", "checkin: de dag telt in NL-tijd")

    # ------------------------------------------------------------------ prikbord
    pb = C.PrikbordCommand(bot)
    r = await run(pb, "prikbord")
    check(r == ["Het prikbord is leeg. Hang iets op met: prikbord <tekst>"], "prikbord leeg")
    r = await run(pb, "prikbord pomp te leen, Weert", name="Piet")
    check(r == ["Opgehangen als #1, 7 dagen zichtbaar."], f"prikbord ophangen: {r}")
    await run(pb, "prikbord ladder te leen", name="Piet")
    r = await run(pb, "prikbord nog eentje", name="Piet")
    check(r == ["Je hebt al 2 berichten hangen. Haal er een weg met: prikbord weg <nr>"], "prikbord: max per persoon")
    r = await run(pb, "prikbord", name="Klaas")
    check(r and r[0].startswith("Prikbord (2): #2 Piet: ladder te leen | #1 Piet: pomp te leen, Weert") and fits(r), f"prikbord lijst, nieuwste eerst: {r}")
    r = await run(pb, "prikbord 1")
    check(r == ["#1 Piet: pomp te leen, Weert (nog 7d)"], f"prikbord <nr>: {r}")
    r = await run(pb, "prikbord weg 1", name="Klaas")
    check(r == ["#1 is niet van jou."], "prikbord: alleen je eigen bericht weghalen")
    r = await run(pb, "prikbord weg 1", name="Piet")
    check(r == ["#1 is weggehaald."], "prikbord weg")
    r = await run(pb, "prikbord " + "x" * 100, name="Klaas")
    check(r == ["Te lang: max 90 bytes."], "prikbord: te lang")
    check(pb.show(2, time.time() + 8 * day) == "#2 staat niet (meer) op het prikbord.", "prikbord: na 7 dagen verlopen")

    # ------------------------------------------------------------------ noodnummers, weetje
    r = await run(C.NoodnummersCommand(bot), "noodnummers")
    check(r == ["Nood: bel 112 (mesh is geen noodlijn) | Politie geen spoed 0900-8844 | Dierenambulance 144"], f"noodnummers standaard: {r}")
    bot_n = make_bot(db, {"Noodnummers_Command": {"numbers": "Huisartsenpost: 088-1234567"}})
    r = await run(C.NoodnummersCommand(bot_n), "nood")
    check(r == ["Nood: bel 112 (mesh is geen noodlijn) | Huisartsenpost: 088-1234567"], "noodnummers met eigen nummers (kaart), 'nood' werkt ook")
    # asked in a channel: the answer goes by DM to the asker; DM impossible -> channel; switch off -> channel
    dms, dm_ok = [], {"v": True}

    async def send_dm_nood(recipient, text, **kw):
        if not dm_ok["v"]:
            return False
        dms.append((recipient, text))
        return True
    bot_d = make_bot(db)
    bot_d.command_manager.send_dm = send_dm_nood
    nood = C.NoodnummersCommand(bot_d)
    r = await run(nood, "noodnummers", name="Piet", channel="#test")
    check(r == [] and dms == [("Piet", "Nood: bel 112 (mesh is geen noodlijn) | Politie geen spoed 0900-8844 | Dierenambulance 144")], f"noodnummers in een kanaal: antwoord als DM aan de vrager, kanaal blijft stil ({dms})")
    dm_ok["v"] = False
    r = await run(nood, "noodnummers", name="Onbekend")
    check(len(r) == 1 and r[0].startswith("Nood: bel 112") and len(dms) == 1, "noodnummers: DM lukt niet -> toch in het kanaal")
    dm_ok["v"] = True
    r = await run(nood, "noodnummers", name="Piet", is_dm=True, pubkey="ab" * 32)
    check(len(r) == 1 and len(dms) == 1, "noodnummers via DM: gewoon antwoord in de DM")
    bot_c = make_bot(db, {"Noodnummers_Command": {"reply_by_dm": "false"}})
    bot_c.command_manager.send_dm = send_dm_nood
    r = await run(C.NoodnummersCommand(bot_c), "noodnummers", name="Piet")
    check(len(r) == 1 and len(dms) == 1, "noodnummers met 'Answer by direct message' uit: antwoord in het kanaal")
    aed = C.AedCommand(bot_d)
    r = await run(aed, "aed", name="Klaas", channel="#test")
    check(r == [] and dms[-1][0] == "Klaas" and dms[-1][1] == TR_NL("commands.aed.usage"), f"aed in een kanaal: antwoord als DM ({dms[-1]})")
    check(any(f["key"] == "reply_by_dm" and f["default"] is True for f in C.AedCommand.settings_schema)
          and any(f["key"] == "reply_by_dm" for f in C.NoodnummersCommand.settings_schema), "aed en noodnummers: kaart-schakelaar 'Answer by direct message', standaard aan")

    from modules.local_data.weetjes import WEETJES
    check(len(WEETJES) >= 50 and all(len(w.encode()) <= 125 for w in WEETJES) and len(set(WEETJES)) == len(WEETJES), "weetjes: genoeg, uniek, elk past in een bericht")
    wt = C.WeetjeCommand(bot)
    seen = set()
    for _ in range(len(WEETJES)):
        seen.update(await run(wt, "weetje"))
    check(seen == set(WEETJES), "weetje: hele lijst voordat er een terugkomt")

    # ------------------------------------------------------------------ peiling
    check(C.parse_poll("15m Waar eten we? | pizza | friet")[0] == 900 and C.parse_poll("Waar? | a")[2] == [], "peiling: duur en te weinig keuzes")
    pl = C.PeilingCommand(bot)
    r = await run(pl, "kies 1")
    check(r == [], "kies zonder lopende peiling: stil")
    r = await run(pl, "peiling Waar eten we? | pizza | friet | chinees")
    check(r == ["Peiling: Waar eten we? 1) pizza 2) friet 3) chinees - stem met kies <nr> (10m)"], f"peiling start: {r}")
    r = await run(pl, "kies 2", name="Piet")
    await run(pl, "kies 2", name="Klaas")
    r2 = await run(pl, "kies 1", name="Piet")
    check(r == ["Stem op friet geteld (0/1/0)"] and r2 == ["Stem op pizza geteld (1/1/0)"], f"kies: stem telt, opnieuw kiezen vervangt: {r} {r2}")
    r = await run(pl, "kies 9", name="Anna")
    check(r == ["Kies een nummer van 1 tot 3."], "kies: ongeldig nummer")
    r = await run(pl, "peiling Nog een? | a | b")
    check(r == ["Er loopt al een peiling. Stop die eerst met: peiling stop"], "peiling: één per kanaal")
    r = await run(pl, "peiling stop")
    check(r == ["Uitslag 'Waar eten we?': pizza 1 | friet 1 | chinees 0 (2 stemmen)"], f"peiling stop: {r}")
    r = await run(pl, "kies 1")
    check(r == [], "kies na het einde: stil")

    # ------------------------------------------------------------------ herinner + Reminders service
    her = C.HerinnerCommand(bot)
    KEY = "ab" * 32
    r = await run(her, "herinner 30m pizza", channel="#test")
    check(r == [], "herinner werkt niet in een kanaal (alleen DM)")
    bot.services["reminders"] = object()
    r = await run(her, "herinner 30m pizza uit de oven", is_dm=True, pubkey=KEY)
    check(len(r) == 1 and r[0].startswith("Herinnering #1 staat voor "), f"herinner 30m: {r}")
    r = await run(her, "herinner 8d te ver", is_dm=True, pubkey=KEY)
    check(r == ["Maximaal 7 dagen vooruit."], "herinner: max 7 dagen")
    await run(her, "herinner 1u twee", is_dm=True, pubkey=KEY)
    await run(her, "herinner 2u drie", is_dm=True, pubkey=KEY)
    r = await run(her, "herinner 3u vier", is_dm=True, pubkey=KEY)
    check(r == ["Je hebt al 3 open herinneringen. Schrap er een met: herinner weg <nr>"], "herinner: max 3 open")
    r = await run(her, "herinner lijst", is_dm=True, pubkey=KEY)
    check(r and r[0].startswith("Open: #1 ") and "#3 " in r[0] and fits(r), f"herinner lijst: {r}")
    r = await run(her, "herinner weg 3", is_dm=True, pubkey="cd" * 32)
    check(r == ["Geen open herinnering #3 van jou."], "herinner: alleen je eigen herinnering schrappen")
    r = await run(her, "herinner weg 3", is_dm=True, pubkey=KEY)
    check(r == ["Herinnering #3 geschrapt."], "herinner weg")
    r = await run(her, "herinner straks iets", is_dm=True, pubkey=KEY)
    check(r and r[0].startswith("Gebruik: herinner 30m"), "herinner: onbekende tijd")
    del bot.services["reminders"]
    r = await run(her, "herinner 2u vijf", is_dm=True, pubkey="ef" * 32)
    check(r and "Reminders-service staat uit" in r[0], "herinner zegt het als de service uit staat")

    sent, ok = [], {"v": True}

    async def send_dm(recipient, text, **kw):
        if not ok["v"]:
            return False
        sent.append((recipient, text))
        return True
    bot.command_manager.send_dm = send_dm
    svc = C.RemindersService(bot)
    later = time.time() + 1900
    n = await svc.deliver_due(later)
    check(n == 1 and sent == [(KEY, "Herinnering: pizza uit de oven")], f"service: de herinnering komt op tijd als DM naar de sleutel: {sent}")
    n = await svc.deliver_due(later + 30)
    check(n == 0 and len(sent) == 1, "service: niet dubbel")
    ok["v"] = False
    n = await svc.deliver_due(later + 3700)
    with db.connection() as c:
        tries, nxt, done = c.execute("SELECT tries, next_try, done FROM community_reminders WHERE id=2").fetchone()
    check(n == 0 and tries == 1 and done == 0 and nxt > later + 3700, "service: mislukt versturen = later opnieuw, niet kwijt")
    for i in range(1, 6):
        await svc.deliver_due(later + 3700 + i * 301)
    with db.connection() as c:
        done = c.execute("SELECT done FROM community_reminders WHERE id=2").fetchone()[0]
    check(done == 2, "service: na 6 pogingen opgegeven")
    ok["v"] = True
    bot2 = make_bot(db)
    bot2.command_manager.send_dm = send_dm
    svc2 = C.RemindersService(bot2)
    await svc2.deliver_due(time.time() + 86400)
    check(any(t == "Herinnering: vijf" for _k, t in sent), "service: na een herstart (nieuwe service, zelfde database) komen open herinneringen nog")
    bot_en = make_bot(db, {"Reminders": {"enabled": "true", "language": "en"}})
    bot_en.get_translator = lambda lang: Translator(lang, "translations/", "local/translations")
    check(C.RemindersService(bot_en).translate("commands.herinner.delivery", text="x") == "Reminder: x", "service: taal van de kaart (en)")

    # ------------------------------------------------------------------ voorspel
    vs = C.VoorspelCommand(bot)
    A, B, Cc = "aa" * 32, "bb" * 32, "cc" * 32
    r = await run(vs, "voorspel")
    check(r and r[0].startswith("Geen open vraag."), "voorspel: geen vraag")
    r = await run(vs, "voorspel nieuw Droog zaterdag? | ja | nee", name="Piet")
    check(r == ["Antwoorden en vragen stellen gaat via een DM aan de bot (daar zit je sleutel bij)."], "voorspel nieuw alleen via DM")
    r = await run(vs, "voorspel nieuw Droog zaterdag? | ja | nee", name="Piet", is_dm=True, pubkey=A)
    check(r and r[0].startswith("Vraag #1 staat open."), f"voorspel nieuw: {r}")
    r = await run(vs, "voorspel nieuw Nog een? | a | b", name="Klaas", is_dm=True, pubkey=B)
    check(r and r[0].startswith("Er is al een open vraag."), "voorspel: één open vraag tegelijk")
    await run(vs, "voorspel 1", name="Piet", is_dm=True, pubkey=A)
    await run(vs, "voorspel 2", name="Klaas", is_dm=True, pubkey=B)
    r = await run(vs, "voorspel 1", name="Klaas", is_dm=True, pubkey=B)
    check(r == ["Genoteerd: 1) ja. Wijzigen kan tot de vraag sluit."], "voorspel: antwoord wijzigen")
    await run(vs, "voorspel 2", name="Anna", is_dm=True, pubkey=Cc)
    r = await run(vs, "voorspel 1", name="Klaas")
    check(r == ["Antwoorden en vragen stellen gaat via een DM aan de bot (daar zit je sleutel bij)."], "voorspel: antwoorden in een kanaal telt niet")
    r = await run(vs, "voorspel")
    check(r == ["Voorspel: Droog zaterdag? 1) ja 2) nee (3 antw., antwoord via DM: voorspel <nr>)"], f"voorspel tonen in het kanaal: {r}")
    r = await run(vs, "voorspel sluit", is_dm=True, pubkey=B)
    check(r == ["Alleen wie de vraag stelde kan dat."], "voorspel: alleen de vrager sluit")
    r = await run(vs, "voorspel sluit", is_dm=True, pubkey=A)
    check(r and r[0].startswith("Gesloten met 3 antwoorden."), "voorspel sluit")
    r = await run(vs, "voorspel 2", name="Klaas", is_dm=True, pubkey=B)
    check(r == ["De vraag is gesloten, antwoorden kan niet meer."], "voorspel: na sluiten geen antwoorden")
    r = await run(vs, "voorspel uitslag 1", is_dm=True, pubkey=A)
    check(r == ["Uitslag: ja. Goed: 2 van 3 (Piet, Klaas), +1 punt."], f"voorspel uitslag: {r}")
    r = await run(vs, "voorspel stand")
    check(r and r[0].startswith("Voorspel stand: 1. ") and "Piet 1" in r[0] and "Klaas 1" in r[0] and "Anna" not in r[0], f"voorspel stand: {r}")
    r = await run(vs, "voorspel nieuw Volgende? | a | b", name="Klaas", is_dm=True, pubkey=B)
    check(r and r[0].startswith("Vraag #2 staat open."), "voorspel: na de uitslag kan een nieuwe vraag")

    # ------------------------------------------------------------------ buien
    raw = "\n".join(f"{v:03d}|{14 + (5 + i * 5) // 60:02d}:{(5 + i * 5) % 60:02d}" for i, v in enumerate([0, 0, 0, 0, 77, 90, 120, 140, 100, 0] + [0] * 14))
    rows = C.parse_raintext(raw)
    check(len(rows) == 24 and rows[0] == ("14:05", 0.0) and rows[4][1] == 0.1 and rows[7][1] == 9.31, f"buien: Buienradar-waarden naar mm/u ({rows[4]}, {rows[7]})")
    marks, start, end, peak, at_ = C.timeline(rows)
    check(len(marks) == 12 and marks.startswith("··▂") and marks[3] == "█" and start == "14:05" and end == "16:00" and at_ == "14:40", f"buien: tijdlijn per 10 min ({marks} {start}-{end} max om {at_})")
    bu = C.BuienCommand(bot)
    text = bu.render(rows, "Weert", 130)
    check(text == f"Buien Weert 14:05-16:00: {marks} max 9,3 mm/u om 14:40" and len(text.encode()) <= 130, f"buien antwoord: {text}")
    check(bu.render(C.parse_raintext("000|14:05\n000|14:10"), "Weert", 130) == "Droog in Weert tot 14:10 (Buienradar).", "buien: droog")

    # ------------------------------------------------------------------ xp + badge
    with db.connection() as c:
        c.execute("INSERT INTO community_activity (name, day, messages, commands) VALUES ('Piet', '2026-01-01', 50, 30)")
        c.commit()
    info = MA.xp_of(bot, "Piet")
    # 8 msgs + 20 (capped from 50) = 28; commands 4 + 10 (capped) = 14 x2 = 28; checkins 3 x5 = 15; karma 1 x10; best hops 5 x5 = 25
    check(info["xp"] == 28 + 28 + 15 + 10 + 25 and info["level"] == 1 and info["next"] == 150, f"xp: berekening met daglimieten ({info['xp']}, level {info['level']})")
    check([MA.level_for(x) for x in (0, 49, 50, 149, 150, 300, 500)] == [0, 0, 1, 1, 2, 3, 4], "xp: levelgrenzen 50, 150, 300, 500")
    with db.connection() as c:
        c.execute("INSERT INTO community_dx (name, day, hops, ts, path) VALUES ('Verre Vera', ?, 31, ?, 'x')", (MC.local_day(bot).isoformat(), now))
        c.execute("INSERT OR REPLACE INTO community_activity (name, day, messages, commands) VALUES ('Verre Vera', ?, 1, 0)", (MC.local_day(bot).isoformat(),))
        c.commit()
    vera = MA.xp_of(bot, "Verre Vera")
    check(vera["best_hops"] == 31 and vera["xp"] == 1 + 50 and "hops6" in MA.badges_of(bot, "Verre Vera"),
          f"xp: beste DX telt tot 10 hops (31 hops = 50 XP, niet 155); de DX-badge blijft gewoon ({vera['xp']})")
    with db.connection() as c:        # remove the test player again, the DX rankings below expect the earlier data
        c.execute("DELETE FROM community_dx WHERE name='Verre Vera'")
        c.execute("DELETE FROM community_activity WHERE name='Verre Vera'")
        c.commit()
    xp = C.XpCommand(bot)
    r = await run(xp, "xp", name="Piet")
    check(r == ["Piet: level 1 Luisteraar, 106 XP (nog 44 tot het volgende level)"], f"xp: {r}")
    r = await run(xp, "xp top")
    check(r and r[0].startswith("XP top (ooit): 1. Piet 106") and "BOT" not in r[0] and OWN not in r[0], f"xp top zonder bots: {r}")
    r = await run(xp, "xp top week")
    check(r and r[0].startswith("XP top (deze week):"), "xp top week")
    r = await run(xp, "xp Niemand")
    check(r == ["Niemand heeft nog geen XP."], "xp: onbekende naam")
    r = await run(C.BadgeCommand(bot), "badge", name="Piet")
    check(r == ["Piet (1/11): 📡3 hops"], f"badge: {r}")
    check("level5" not in MA.badges_of(bot, "Piet"), "badge: level 5 nog niet gehaald")
    r = await run(C.BadgeCommand(bot), "badge Niemand")
    check(r == ["Niemand heeft nog geen badges."], "badge: niemand")

    # ------------------------------------------------------------------ Community service
    csvc = C.CommunityService(bot)
    check(csvc.config_section == "Community" and csvc.get_metadata()["name"] == "community", "Community-service: kaart en naam")
    check(C.RemindersService(bot).get_metadata()["name"] == "reminders", "Reminders-service: naam 'reminders' (herinner kijkt daarnaar)")

    # ------------------------------------------------------------------ Games page (dashboard)
    from modules import games_admin
    with db.connection() as c:
        c.execute("INSERT OR REPLACE INTO community_activity (name, day, messages, commands) VALUES ('BE-ExampleNode-BOT', ?, 20, 10)", (MC.local_day(bot).isoformat(),))
        c.execute("INSERT INTO community_karma (giver, receiver, day, ts) VALUES ('Piet', '🤖Helper', '2026-09-01', 1)")
        c.commit()
    C.CheckinCommand(bot).check_in("Klaas", time.time())   # a streak that is running today, whatever day the tests run
    g = games_admin.standings(db, bot.config, logging.getLogger("games"))
    raw = json.dumps(g, ensure_ascii=False)
    for period in ("ever", "week"):
        rows = g["xp"][period]
        check(rows and all(sum(p["xp"] for p in r["parts"]) == r["xp"] for r in rows)
              and all([p["key"] for p in r["parts"]] == ["messages", "commands", "checkins", "karma", "dx"] for r in rows),
              f"games ({period}): de XP-opbouw per persoon telt precies op tot de totale XP")
    piet = g["xp"]["ever"][0]
    check({p["key"]: (p["count"], p["xp"]) for p in piet["parts"]} == {"messages": (28, 28), "commands": (14, 28), "checkins": (3, 15), "karma": (1, 10), "dx": (5, 25)},
          f"games: opbouw van Piet klopt (28 berichten, 14 commando's x2, 3 check-ins x5, 1 karma x10, 5 hops x5) {piet['parts']}")
    check([r["name"] for r in g["xp"]["ever"]][:1] == ["Piet"] and g["xp"]["ever"][0]["level"] == 1 and g["xp"]["ever"][0]["title"] == 1, f"games: XP-stand met level en titel ({g['xp']['ever'][:2]})")
    check(g["dx"]["ever"][0] == {"name": "Oude Jan", "hops": 8, "date": "05-01-2025"} and g["dx"]["week"][0]["name"] == "Piet", "games: DX week/ooit")
    check("BOT" not in raw and "Helper" not in raw and OWN not in raw, "games: geen enkele bot in de standen")
    check(A not in raw and B not in raw and "abab" not in raw, "games: geen publieke sleutels naar de browser")
    check(g["voorspel"]["question"]["text"] == "Volgende?" and [c["answers"] for c in g["voorspel"]["question"]["choices"]] == [0, 0] and {r["name"] for r in g["voorspel"]["standings"]} == {"Piet", "Klaas"}, "games: open voorspelvraag en stand")
    check(g["checkin"] and g["checkin"][0]["name"] == "Klaas" and g["f1"] == {"season": None, "standings": [], "open": None} and g["badges_total"] == 11, f"games: check-in, F1 (nog leeg) ({g['checkin']})")
    # F1: a prediction shows up at once as an open round (names only), and in the standings once the race is scored
    from modules.f1_game import F1Game
    f1g = F1Game(db)
    f1g.ensure_tables()
    check(games_admin.standings(db, bot.config)["f1"] == {"season": None, "standings": [], "open": None}, "games: F1-tabellen leeg = niets open")
    for key, who, code in (("aa" * 32, "Piet", "VER"), ("bb" * 32, "BE-ExampleNode-BOT", "HAM"), ("cc" * 32, "Klaas", "NOR")):
        f1g.predict("2026", "18", key, who, code, 1000.0, None, set(), lambda k, **kw: k)
    f1 = games_admin.standings(db, bot.config)["f1"]
    check(f1 == {"season": "2026", "standings": [], "open": {"season": "2026", "round": "18", "names": ["Piet", "Klaas"]}},
          f"games: open F1-ronde met namen (zonder bots, zonder keuzes) {f1}")
    f1raw = json.dumps(f1)
    check("VER" not in f1raw and "NOR" not in f1raw and "aaaa" not in f1raw, "games: F1-keuzes en sleutels blijven verborgen tot de telling")
    f1g.score("2026", "18", [{"pos": "1", "code": "VER"}, {"pos": "2", "code": "NOR"}, {"pos": "3", "code": "LEC"}])
    f1 = games_admin.standings(db, bot.config)["f1"]
    check(f1["open"] is None and [(r["name"], r["races"]) for r in f1["standings"]] == [("Piet", 1), ("Klaas", 1)] and f1["standings"][0]["points"] > f1["standings"][1]["points"] > 0,
          f"games: na de telling staat de ronde in de stand en niet meer open {f1}")
    f1g.predict("2026", "19", "aa" * 32, "Piet", "PIA", 2000.0, None, set(), lambda k, **kw: k)
    check(games_admin.standings(db, bot.config)["f1"]["open"] == {"season": "2026", "round": "19", "names": ["Piet"]}, "games: volgende ronde weer open")

    # ------------------------------------------------------------------ bare 'help' links to the full command list
    from modules.command_manager import CommandManager
    from modules.commands.help_command import HelpCommand
    URL = "https://github.com/example/meshcore-bot-commands"
    for lang, expect in (("nl", f"Alle commando's met uitleg: {URL} | help <commando> = uitleg hier"),
                         ("en", f"All commands explained: {URL} | help <command> = help here")):
        b = make_bot(db, {"Help_Command": {"list_url": URL}})
        b.translator = Translator(lang, "translations/", "local/translations")
        b.config["Localization"] = {"language": lang}
        hc = HelpCommand(b)
        fake = types.SimpleNamespace(bot=b, commands={"help": hc, "dx": C.DxCommand(b)})
        text = CommandManager.get_general_help(fake, MeshMessage(content="help", sender_id="Piet", channel="#test"))
        check(text == expect and len(text.encode()) <= 130, f"help ({lang}) met link op de kaart: {text!r}")
    b = make_bot(db)
    fake = types.SimpleNamespace(bot=b, commands={"help": HelpCommand(b), "dx": C.DxCommand(b)})
    text = CommandManager.get_general_help(fake, MeshMessage(content="help", sender_id="Piet", channel="#test"))
    check(text.startswith("Help: ") and "helpall=alles" in text and "github" not in text, f"help zonder link: zoals vroeger ({text!r})")
    check(any(f["key"] == "list_url" and f["default"] == "" for f in HelpCommand.settings_schema), "help-kaart heeft het veld 'Link to the full command list', standaard leeg")
    check(Translator("nl", "translations/", "local/translations").translate("commands.help.general", commands_list="x") != "commands.help.general", "upstream's eigen help-teksten blijven werken naast de nieuwe sleutel")

    # ------------------------------------------------------------------ hint text variants (test in the public channel)
    from modules.channel_hint import ChannelHint
    posted = []

    async def send_channel_message(channel, text, **kw):
        posted.append((channel, text))
        return True
    variants = "We helpen je heel graag verder in {channels} || Voor de bot ben je welkom in {channels} || Tip: probeer {channels}"
    bot_h = make_bot(db, {"ChannelHint": {"enabled": "true", "channels": "Publiek", "where": "#test", "message": variants, "yield_seconds": "0"}})
    bot_h.command_manager.send_channel_message = send_channel_message
    hint = ChannelHint(bot_h)
    for i in range(30):
        hint._last_channel.clear()
        hint._last_user.clear()
        await hint.send_hint(MeshMessage(content="test", sender_id=f"P{i}", channel="Publiek"))
    texts = [t for _c, t in posted]
    check(len(texts) == 30 and set(texts) == {"We helpen je heel graag verder in #test", "Voor de bot ben je welkom in #test", "Tip: probeer #test"},
          f"hint in Publiek: willekeurig een van de varianten, {{channels}} ingevuld ({set(texts)})")
    check(all(a != b for a, b in zip(texts, texts[1:])), "hint: nooit twee keer achter elkaar dezelfde tekst")
    posted.clear()
    bot_1 = make_bot(db, {"ChannelHint": {"enabled": "true", "channels": "Publiek", "where": "#test", "message": "Kom naar {channels}", "yield_seconds": "0"}})
    bot_1.command_manager.send_channel_message = send_channel_message
    h1 = ChannelHint(bot_1)
    for i in range(3):
        h1._last_channel.clear()
        h1._last_user.clear()
        await h1.send_hint(MeshMessage(content="test", sender_id="Piet", channel="Publiek"))
    check([t for _c, t in posted] == ["Kom naar #test"] * 3, "hint met één tekst (zonder ||) werkt als vroeger")
    from modules.channel_hint import DEFAULT_MESSAGE
    check(len(DEFAULT_MESSAGE.split("||")) == 4 and all(len(v.strip().replace("{channels}", "#bot, #test").encode()) <= 130 for v in DEFAULT_MESSAGE.split("||")),
          "standaard hint-tekst: 4 varianten, elk past in een bericht")

    # ------------------------------------------------------------------ kenteken: Belgian and German plates
    from modules.commands.kenteken_command import foreign_country, looks_german
    check(foreign_country("1-ABC-234") == "be" and foreign_country("1abc234") == "be" and foreign_country("be 1-ABC-23") == "be", "kenteken: Belgisch herkend (1-ABC-234, of met 'be' ervoor)")
    check(foreign_country("d M-AB 1234") == "de" and looks_german("M-AB 1234") and looks_german("B AB 123E"), "kenteken: Duits herkend (M-AB 1234, of met 'd' ervoor)")
    check(foreign_country("HDJ-60-R") == "" and foreign_country("1-ABC-23") == "" and not looks_german("12-AB-34") and not looks_german("X-999-XX"), "kenteken: Nederlandse kentekens niet als buitenlands gezien")
    ken = C.KentekenCommand(bot)
    r = await run(ken, "kenteken 1-ABC-234")
    check(r == ["Belgisch kenteken: daar is geen gratis open bron voor (de DIV deelt niets), alleen Nederlandse kentekens via de RDW."], f"kenteken Belgisch: antwoord zonder opzoeken ({r})")
    r = await run(ken, "kenteken d M-AB 1234")
    check(r and r[0].startswith("Duits kenteken:"), "kenteken Duits met landwoord")

    # ------------------------------------------------------------------ rptr / f1 follow their service (1.0.0: nothing of someone else's setup)
    from modules.commands.rptr_command import RptrCommand
    from modules.commands.f1_command import F1Command
    check(not import_with_stubs(lambda: RptrCommand(make_bot(db))).rptr_enabled and RptrCommand(make_bot(db, {"HARepeater": {"enabled": "true"}})).rptr_enabled,
          "rptr staat alleen aan als HARepeater aan staat (anders niet in help, en 'staat uit' als je het typt)")
    check(not F1Command(make_bot(db)).f1_enabled and F1Command(make_bot(db, {"F1": {"enabled": "true"}})).f1_enabled,
          "f1 staat alleen aan als de F1-service aan staat")
    check(not F1Command(make_bot(db, {"F1": {"enabled": "true"}, "F1_Command": {"enabled": "false"}})).f1_enabled, "f1 met eigen schakelaar uit blijft uit")

    # ------------------------------------------------------------------ switches, keywords
    for cls, section in ((C.DxCommand, "Dx_Command"), (C.PadCommand, "Pad_Command"), (C.SigCommand, "Sig_Command"), (C.KarmaCommand, "Karma_Command"),
                         (C.PrikbordCommand, "Prikbord_Command"), (C.XpCommand, "Xp_Command"), (C.BuienCommand, "Buien_Command")):
        b = make_bot(db, {section: {"enabled": "false"}})
        cmd = cls(b)
        check(not cmd.can_execute(MeshMessage(content=cls.keywords[0], sender_id="Piet", channel="#test")), f"{cls.__name__}: schakelaar uit = geen antwoord")
        check(cmd._derive_config_section_name() == section, f"{cls.__name__}: kaart hoort bij [{section}]")
    import glob
    import importlib
    all_kw = {}
    for f in sorted(glob.glob("modules/commands/*_command.py")):
        mod = import_with_stubs(lambda: importlib.import_module("modules.commands." + os.path.basename(f)[:-3]))
        for obj in vars(mod).values():
            if isinstance(obj, type) and obj.__module__ == mod.__name__ and getattr(obj, "keywords", None) and getattr(obj, "name", ""):
                for k in obj.keywords:
                    all_kw.setdefault(k.lower(), set()).add(obj.name)
    new = ["dx", "pad", "sig", "signaal", "meshkaart", "nodes", "karma", "topkarma", "checkin", "meld", "inchecken", "prikbord", "noodnummers", "nood",
           "weetje", "wistje", "peiling", "kies", "herinner", "remind", "voorspel", "buien", "buienradar", "xp", "level", "badge", "badges"]
    clashes = {k: sorted(all_kw.get(k, ())) for k in new if len(all_kw.get(k, ())) != 1}
    check(not clashes, f"nieuwe trefwoorden botsen niet met bestaande commando's {clashes}")

    print(f"\n{len(fails)} fouten")
    return 1 if fails else 0


sys.exit(asyncio.run(main()))
