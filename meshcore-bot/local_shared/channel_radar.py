#!/usr/bin/env python3
"""Kanaalradar: which hashtag channels are in use around the bot (service: local_service_plugins/channel_radar_service.py,
dashboard: the Channel radar page).

A group message (GRP_TXT) starts with one byte that identifies its channel - the first byte of SHA256(channel key) - and
a 2-byte MAC (HMAC-SHA256 over the encrypted text, key = channel key + 16 zero bytes). The key of a hashtag channel is
the first 16 bytes of SHA256("#name"). So for a list of candidate names the radar can say for certain which channel a
message belongs to (hash and MAC both match; a wrong name passes the MAC only once in 65 536) - without decrypting it.
Messages on channels whose name is not in the list (private channels, names nobody thought of) are counted per channel
byte as "unknown". Nothing is ever sent, and message texts are never read.

Tables (the bot's own database):
  channel_radar        (day, label, messages, last_ts)    per recognised channel per local day
  channel_radar_other  (day, hash, messages, last_ts)     per unknown channel byte per local day
"""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import timedelta
from typing import Any, Iterable, Optional

from .mesh_community import local_day

PUBLIC_LABEL = "Publiek (kanaal 0)"
PUBLIC_KEY = bytes.fromhex("8b3387e9c5cdea6ac9e5edbaa115cd72")   # MeshCore's well-known public channel

# Names people use or might use in the Netherlands, Belgium and Germany. Anyone can add more on the card.
DEFAULT_NAMES = """
test bot f1 p2000 p2000-nl p2000-zl p2000-li p2000-limburg
ardf vpk nl-noord hunebedronde testnoord afrithonbot
nl be de nederland belgie belgië deutschland europe eu euregio emr benelux
limburg zuid-limburg zuidlimburg zl nl-zuid nl-li nl-lim nl-limburg li lim nl-oost nl-west nl-midden nl-zh nl-nh nl-gld nl-nb
nl-ov nl-ut nl-fl nl-ze nl-gr nl-fr nl-dr brabant noord-brabant gelderland utrecht zeeland friesland drenthe groningen overijssel
parkstad maastricht heerlen sittard geleen roermond venlo weert kerkrade landgraaf eindhoven nijmegen amsterdam rotterdam
denhaag den-haag be-li be-lim limburg-be vlaanderen wallonie antwerpen genk hasselt brussel gent leuven luik liege tongeren
nrw de-nw d-nrw aachen koeln köln eifel heinsberg dusseldorf düsseldorf rheinland
mesh meshcore meshnl mesh-nl meshbe mesh-be meshde nlmesh general algemeen chat praat kletsen gezellig lobby cafe koffie
help hulp vragen support beginners welkom welcome testing testen bots testbot
weer weather wx meteo weerstation storm onweer knmi nieuws news emergency noodgeval nood 112 alarm rampen nlalert sos
ham hamradio radio amateur pa on dl sota pota aprs dx cb 27mc pmr lora lorawan meshtastic ttn
repeater repeaters sysop admin beheer netwerk network tech techniek dev firmware hardware esp32 heltec rak tbeam homeassistant ha
diy events meetup markt tekoop te-koop sport voetbal formule1 racing games spel quiz fun verkeer file ov trein space iss astro
""".split()


# Generated names: every base word with common prefixes and suffixes (mesh-zl, nl-limburg, maastricht-chat, ...).
# Tens of thousands of names, but a message is only checked against the few that share its channel byte. A generated
# name is only shown after 2 messages, so a chance match (1 in 65 536 per name) never makes the list on its own.
GEN_WORDS = """
limburg zuid-limburg zuidlimburg noord-limburg midden-limburg zl li lim maasland parkstad westelijke-mijnstreek mijnstreek heuvelland
maastricht heerlen sittard geleen roermond venlo weert kerkrade brunssum landgraaf valkenburg meerssen stein beek echt susteren gulpen
vaals simpelveld voerendaal nuth schinveld onderbanken hoensbroek born elsloo eijsden margraten venray horst panningen tegelen
aachen aken heinsberg geilenkirchen eschweiler stolberg herzogenrath alsdorf wurselen duren düren koln köln cologne bonn eifel
nrw rheinland euregio emr dreiländereck drielandenpunt genk hasselt tongeren maaseik lanaken maasmechelen bree lommel sint-truiden
luik liege leuven brussel antwerpen gent brugge vlaanderen wallonie limburg-be eindhoven helmond tilburg breda den-bosch nijmegen
arnhem utrecht amsterdam rotterdam denhaag den-haag haarlem leiden zwolle enschede groningen leeuwarden assen almere apeldoorn
nederland holland belgie belgië deutschland nl be de lu eu benelux europe
mesh meshcore meshtastic lora chat general algemeen praat kletsen cafe lobby welkom help hulp vragen info test testen bot bots
weer weather wx meteo nieuws news p2000 112 alarm nood noodgeval emergency rampen sos
ham hamradio radio amateur pa on dl sota pota aprs cb pmr dx contest
repeater repeaters sysop admin beheer netwerk tech dev firmware hardware diy maker homeassistant
events meetup markt sport voetbal f1 formule1 games quiz fun muziek music food eten fietsen motor auto
""".split()
GEN_PREFIXES = ["", "nl-", "be-", "de-", "mesh-", "meshcore-", "nl", "be", "de", "mesh"]
GEN_SUFFIXES = ["", "-nl", "-be", "-de", "nl", "be", "de", "-mesh", "mesh", "-chat", "chat", "-li", "-zl", "-lim",
                "-test", "test", "-bot", "bot", "1", "2", "-1", "-2", "-mc", "mc", "-meshcore", "-lora", "-radio", "-weer", "-info"]


def generated_names() -> list:
    out = []
    for word in GEN_WORDS:
        for pre in GEN_PREFIXES:
            for suf in GEN_SUFFIXES:
                out.append(pre + word + suf)
    return out


def key_for_name(name: str) -> bytes:
    """Key of a hashtag channel: the first 16 bytes of SHA256 of its lowercase name with '#'."""
    name = name.strip().lower()
    if not name.startswith("#"):
        name = "#" + name
    return hashlib.sha256(name.encode("utf-8")).digest()[:16]


def channel_byte(key16: bytes) -> int:
    return hashlib.sha256(key16).digest()[0]


def build_table(names: Iterable[str], generated: Iterable[str] = ()) -> dict:
    """{channel byte: [(label, key16), ...]} for the public channel and every name; `names` first, so a name on the
    main list wins over the same generated one."""
    table: dict = {channel_byte(PUBLIC_KEY): [(PUBLIC_LABEL, PUBLIC_KEY)]}
    seen = {PUBLIC_LABEL}
    for raw in list(names) + list(generated):
        name = raw.strip().lower().lstrip("#")
        if not name or "#" + name in seen:
            continue
        seen.add("#" + name)
        key = key_for_name(name)
        table.setdefault(channel_byte(key), []).append(("#" + name, key))
    return table


def identify(payload_hex: str, table: dict) -> tuple:
    """(label or None, channel byte as 2-hex) for one GRP_TXT payload. Never decrypts."""
    try:
        raw = bytes.fromhex(payload_hex)
    except (ValueError, TypeError):
        return None, None
    if len(raw) < 4:
        return None, None
    ch, mac, ciphertext = raw[0], raw[1:3], raw[3:]
    for label, key in table.get(ch, []):
        calc = hmac.new(key + bytes(16), ciphertext, hashlib.sha256).digest()[:2]
        if hmac.compare_digest(calc, mac):
            return label, f"{ch:02x}"
    return None, f"{ch:02x}"


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS channel_radar (
        day TEXT NOT NULL, label TEXT NOT NULL, messages INTEGER NOT NULL DEFAULT 0, last_ts INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, label))""",
    """CREATE TABLE IF NOT EXISTS channel_radar_other (
        day TEXT NOT NULL, hash TEXT NOT NULL, messages INTEGER NOT NULL DEFAULT 0, last_ts INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, hash))""",
]


def ensure_tables(db: Any) -> None:
    with db.connection() as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()


def record(conn: Any, day: str, label: Optional[str], ch_hex: str, ts: int) -> None:
    if label:
        conn.execute("""INSERT INTO channel_radar (day, label, messages, last_ts) VALUES (?,?,1,?)
                        ON CONFLICT(day, label) DO UPDATE SET messages = messages + 1, last_ts = MAX(last_ts, excluded.last_ts)""",
                     (day, label, ts))
    else:
        conn.execute("""INSERT INTO channel_radar_other (day, hash, messages, last_ts) VALUES (?,?,1,?)
                        ON CONFLICT(day, hash) DO UPDATE SET messages = messages + 1, last_ts = MAX(last_ts, excluded.last_ts)""",
                     (day, ch_hex, ts))


def main_names(bot: Any) -> set:
    """Labels that are shown from the first message: the built-in list and the names on the card."""
    extra = ""
    if bot.config.has_section("ChannelRadar"):
        extra = bot.config.get("ChannelRadar", "extra_names", fallback="") or ""
    names = list(DEFAULT_NAMES) + [n for n in str(extra).split(",") if n.strip()]
    return {PUBLIC_LABEL} | {"#" + n.strip().lower().lstrip("#") for n in names}


def names_signature(names: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(set(n.strip().lower().lstrip("#") for n in names))).encode()).hexdigest()[:16]


def summary(bot: Any, now_ts: Optional[float] = None) -> dict:
    """What the dashboard page shows: every recognised channel with today / 7 days / 30 days / last seen, and the unknown ones."""
    now_ts = time.time() if now_ts is None else now_ts
    today = local_day(bot, now_ts)
    d7, d30 = (today - timedelta(days=6)).isoformat(), (today - timedelta(days=29)).isoformat()
    ensure_tables(bot.db_manager)
    with bot.db_manager.connection() as conn:
        rows = conn.execute(
            """SELECT label, SUM(CASE WHEN day = ? THEN messages ELSE 0 END), SUM(CASE WHEN day >= ? THEN messages ELSE 0 END),
                      SUM(messages), MAX(last_ts), MIN(day)
               FROM channel_radar WHERE day >= ? GROUP BY label ORDER BY 3 DESC, 4 DESC""",
            (today.isoformat(), d7, d30)).fetchall()
        other = conn.execute(
            """SELECT hash, SUM(CASE WHEN day >= ? THEN messages ELSE 0 END), SUM(messages), MAX(last_ts)
               FROM channel_radar_other WHERE day >= ? GROUP BY hash ORDER BY 2 DESC, 3 DESC""", (d7, d30)).fetchall()
        first = conn.execute("SELECT MIN(day) FROM channel_radar").fetchone()[0]
        first_other = conn.execute("SELECT MIN(day) FROM channel_radar_other").fetchone()[0]
    since = min(d for d in (first, first_other) if d) if (first or first_other) else None
    main = main_names(bot)
    return {
        "generated_at": int(now_ts),
        "since": since,
        "channels": [{"label": r[0], "today": int(r[1] or 0), "week": int(r[2] or 0), "month": int(r[3] or 0),
                      "last_ts": int(r[4] or 0), "first_day": r[5], "found": r[0] not in main}
                     for r in rows if r[0] in main or int(r[3] or 0) >= 2],
        "unknown": [{"hash": r[0], "week": int(r[1] or 0), "month": int(r[2] or 0), "last_ts": int(r[3] or 0)} for r in other],
    }
