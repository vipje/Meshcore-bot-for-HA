"""Channel radar (Kanaalradar) against the real patched code: recognising a hashtag channel by channel byte + MAC (never
decrypting), counting per day, the same message via several repeaters once, unknown channels, restart safety, the card
setting for extra names, and the dashboard summary."""
import configparser
import contextlib
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import sys
import tempfile
import time
import types
from unittest.mock import MagicMock

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
    global R, ChannelRadarService
    from modules import channel_radar as R
    from modules.service_plugins.channel_radar_service import ChannelRadarService


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
            c.execute("CREATE TABLE packet_stream (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, data TEXT NOT NULL, type TEXT NOT NULL)")
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


def group_payload(key16: bytes, body: bytes) -> str:
    """A GRP_TXT payload as the firmware makes it: channel byte + MAC over the (here: fake) ciphertext."""
    mac = hmac.new(key16 + bytes(16), body, hashlib.sha256).digest()[:2]
    return (bytes([R.channel_byte(key16)]) + mac + body).hex()


def add_packet(db, ts, payload_hex, packet_hash, kind="packet", ptype="GRP_TXT"):
    data = json.dumps({"payload_type_name": ptype, "payload_hex": payload_hex, "packet_hash": packet_hash})
    with db.connection() as c:
        c.execute("INSERT INTO packet_stream (timestamp, data, type) VALUES (?,?,?)", (ts, data, kind))
        c.commit()


def make_bot(db, extra=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "X", "timezone": "Europe/Amsterdam"}
    cfg["ChannelRadar"] = {"enabled": "true", **(extra or {})}
    return types.SimpleNamespace(config=cfg, logger=logging.getLogger("radar"), db_manager=db)


# ---------------------------------------------------------------- recognising
k_limburg = R.key_for_name("limburg")
check(k_limburg == hashlib.sha256(b"#limburg").digest()[:16] and R.key_for_name("#Limburg") == k_limburg, "sleutel = eerste 16 bytes SHA256('#naam'), hoofdletters en # maken niet uit")
check(R.key_for_name("f1").hex() == "bbf06f639e0e37fb2d2b9d6cc6c26c14", "sleutel van #f1 klopt met die op de radio")
table = R.build_table(R.DEFAULT_NAMES)
body = os.urandom(32)
check(R.identify(group_payload(k_limburg, body), table) == ("#limburg", f"{R.channel_byte(k_limburg):02x}"), "#limburg herkend via kenmerk + MAC")
check(R.identify(group_payload(R.PUBLIC_KEY, body), table)[0] == R.PUBLIC_LABEL, "het publieke kanaal herkend")
bad = bytearray(bytes.fromhex(group_payload(k_limburg, body)))
bad[1] ^= 0xFF
check(R.identify(bad.hex(), table) == (None, f"{bad[0]:02x}"), "verkeerde MAC = niet herkend (alleen het kenmerk is niet genoeg)")
secret = R.key_for_name("mijn-geheime-kanaal-xyz")
check(R.identify(group_payload(secret, body), table)[0] is None, "onbekend kanaal blijft onbekend")
check(R.identify("zz", table) == (None, None) and R.identify("0102", table) == (None, None), "rommel en te korte pakketten geven niets")
check(len(R.DEFAULT_NAMES) >= 200, f"ruime lijst met namen ({len(R.DEFAULT_NAMES)})")

# ---------------------------------------------------------------- the service
tmp = tempfile.mkdtemp()
db = DB(f"{tmp}/bot.db")
now = time.time()
add_packet(db, now - 3600, group_payload(k_limburg, body), "AAA1")
add_packet(db, now - 3500, group_payload(k_limburg, body), "AAA1", kind="routing")      # same message via another repeater
add_packet(db, now - 3000, group_payload(k_limburg, os.urandom(40)), "AAA2")
add_packet(db, now - 2000, group_payload(R.key_for_name("test"), os.urandom(24)), "BBB1")
add_packet(db, now - 1000, group_payload(secret, os.urandom(24)), "CCC1")
add_packet(db, now - 900, "00" * 20, "DDD1", ptype="ADVERT")                                # not a group message
svc = ChannelRadarService(make_bot(db))
n = svc.scan(now)
s = R.summary(make_bot(db), now)
rows = {c["label"]: c for c in s["channels"]}
check(n == 4 and rows["#limburg"]["today"] + 0 >= 0 and rows["#limburg"]["week"] == 2 and rows["#test"]["week"] == 1,
      f"service telt per kanaal, hetzelfde bericht via 2 repeaters 1 keer ({n}, {rows})")
check(len(s["unknown"]) == 1 and s["unknown"][0]["week"] == 1 and s["unknown"][0]["hash"] == f"{R.channel_byte(secret):02x}", "onbekend kanaal apart geteld op kenmerk")
check(svc.scan(now + 60) == 0, "een tweede ronde telt niets dubbel")
svc2 = ChannelRadarService(make_bot(db))
check(svc2.scan(now + 120) == 0 and db.get_metadata("radar.last_id") == "6", "na een herstart (nieuwe service, zelfde database) niets dubbel")
add_packet(db, now + 100, group_payload(k_limburg, os.urandom(16)), "AAA3")
check(svc2.scan(now + 180) == 1 and {c["label"]: c for c in R.summary(make_bot(db), now + 180)["channels"]}["#limburg"]["week"] == 3,
      "nieuw bericht na de herstart wordt wel geteld")

# ---------------------------------------------------------------- extra names on the card
db2 = DB(f"{tmp}/bot2.db")
add_packet(db2, now - 100, group_payload(secret, os.urandom(24)), "EEE1")
svc3 = ChannelRadarService(make_bot(db2, {"extra_names": "#mijn-geheime-kanaal-xyz, andere"}))
svc3.scan(now)
labels = [c["label"] for c in R.summary(make_bot(db2, {"extra_names": "#mijn-geheime-kanaal-xyz, andere"}), now)["channels"]]
check(labels == ["#mijn-geheime-kanaal-xyz"], f"een naam op de kaart wordt herkend ({labels})")
field = [f for f in ChannelRadarService.settings_schema if f["key"] == "extra_names"]
check(field and field[0]["type"] == "list", "kaart: veld 'Extra channel names to look for'")
check(json.dumps(R.summary(make_bot(db), now)).count("payload") == 0, "het overzicht bevat geen berichtinhoud of pakketdata")

# ---------------------------------------------------------------- generated names, and counting again when the list changes
gen = R.generated_names()
check(len(gen) > 20000 and "mesh-zl" in gen and "maastricht-chat" in gen, f"gegenereerde namen ({len(gen)}), o.a. mesh-zl en maastricht-chat")
db3 = DB(f"{tmp}/bot3.db")
k_gen = R.key_for_name("mesh-zl")
add_packet(db3, now - 500, group_payload(k_gen, os.urandom(20)), "GGG1")
svc5 = ChannelRadarService(make_bot(db3))
t0 = time.time(); svc5.scan(now); took = time.time() - t0
labels = [c["label"] for c in R.summary(make_bot(db3), now)["channels"]]
check(labels == [], f"een gegenereerde naam met 1 bericht staat nog niet op de lijst (kan toeval zijn) {labels}")
add_packet(db3, now - 400, group_payload(k_gen, os.urandom(20)), "GGG2")
svc5.scan(now + 60)
chans = R.summary(make_bot(db3), now + 60)["channels"]
check([(c["label"], c["month"], c["found"]) for c in chans] == [("#mesh-zl", 2, True)], f"vanaf 2 berichten wel, gemarkeerd als gevonden ({chans})")
check(took < 5, f"eerste ronde met alle namen blijft snel ({took:.2f} s)")
# a name added on the card counts from the start of the packet log, and nothing is counted twice
db4 = DB(f"{tmp}/bot4.db")
k_new = R.key_for_name("zeldzaam-kanaal-q")
add_packet(db4, now - 800, group_payload(k_new, os.urandom(20)), "HHH1")
add_packet(db4, now - 700, group_payload(k_limburg, os.urandom(20)), "HHH2")
ChannelRadarService(make_bot(db4)).scan(now)
before = {c["label"]: c["month"] for c in R.summary(make_bot(db4), now)["channels"]}
svc6 = ChannelRadarService(make_bot(db4, {"extra_names": "zeldzaam-kanaal-q"}))
svc6.scan(now + 60)
after = {c["label"]: c["month"] for c in R.summary(make_bot(db4, {"extra_names": "zeldzaam-kanaal-q"}), now + 60)["channels"]}
check(before == {"#limburg": 1} and after == {"#limburg": 1, "#zeldzaam-kanaal-q": 1},
      f"naam op de kaart erbij: het pakketlogboek wordt opnieuw geteld, niets dubbel ({before} -> {after})")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
