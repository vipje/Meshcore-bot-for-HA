"""Bots-pagina op de echte gepatchte v1.1.0-viewer, met voorbeelddata."""
import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import configparser, json, os, re, sys, tempfile, time, types

TREE = sys.argv[1]
os.chdir(TREE); sys.path.insert(0, TREE)

work = tempfile.mkdtemp()
OWN = "Mesh|HA|🤖"
cfg = configparser.ConfigParser()
cfg["Bot"] = {"db_path": f"{work}/viewer.db", "bot_name": OWN}
cfg["Web_Viewer"] = {"enabled": "true", "web_viewer_password": ""}
cfg["Channels"] = {"monitor_channels": "#test"}
open(f"{work}/config.ini", "w").write("")
with open(f"{work}/config.ini", "w") as f:
    cfg.write(f)

from modules.web_viewer.app import BotDataViewer
viewer = BotDataViewer(config_path=f"{work}/config.ini")
app = viewer.app
app.config["TESTING"] = True

XSS = '<img src=x onerror=alert(1)>Bot'
now = int(time.time())
with viewer.db_manager.connection() as conn:
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS message_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER NOT NULL, sender_id TEXT NOT NULL, channel TEXT,
        content TEXT NOT NULL, is_dm BOOLEAN NOT NULL, hops INTEGER, snr REAL, rssi INTEGER, path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    rows = [("DX1ABC-BOT", 8, now - 60), ("Alex", 30, now - 30), ("Klapperdeklap", 5, now - 4000), ("Botond", 2, now - 500),
            ("Talbot", 3, now - 900), (XSS, 1, now - 20), (OWN, 9, now - 5), ("Echo  Bot 2", 1, now - 7000)]
    for name, n, ts in rows:
        for i in range(n):
            c.execute("INSERT INTO message_stats (timestamp, sender_id, channel, content, is_dm) VALUES (?,?,?,?,0)",
                      (ts - i, name, "#test", "hi"))
    c.execute("INSERT INTO message_stats (timestamp, sender_id, channel, content, is_dm) VALUES (?,?,?,?,1)",
              (now, "DmOnly", None, "hi"))
    cols = {r[1]: r for r in c.execute("PRAGMA table_info(complete_contact_tracking)").fetchall()}
    def contact(key, name, role):
        vals = {"public_key": key, "name": name, "role": role, "device_type": "1",
                "first_heard": "2026-09-01 10:00:00", "last_heard": "2026-09-21 16:20:12"}
        for cname, (_, _, ctype, notnull, default, _) in cols.items():
            if cname in vals or cname == "id" or not notnull or default is not None:
                continue
            vals[cname] = 0 if "INT" in (ctype or "").upper() or "REAL" in (ctype or "").upper() else ""
        c.execute(f"INSERT INTO complete_contact_tracking ({','.join(vals)}) VALUES ({','.join('?'*len(vals))})", list(vals.values()))
    contact("aa" * 32, "Echobot", "companion")
    contact("bb" * 32, "Gewone Companion", "companion")
    conn.commit()

client = app.test_client()
fails = []
def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

# 1. pagina + navigatie
r = client.get("/bots"); html = r.get_data(as_text=True)
check(r.status_code == 200 and "Bots" in html, "GET /bots geeft de pagina")
check('href="/bots"' in client.get("/").get_data(as_text=True), "navigatiebalk heeft een Bots-item")
tpl = open(os.path.join(TREE, "modules/web_viewer/templates/bots.html"), encoding="utf-8").read()
check("innerHTML" not in tpl and "insertAdjacentHTML" not in tpl and "document.write" not in tpl, "sjabloon gebruikt geen innerHTML")

# 2. lijst
r = client.get("/api/bots"); data = r.get_json()
by = {n["name"]: n for n in data["names"]}
check(r.status_code == 200, "GET /api/bots werkt")
check(by["DX1ABC-BOT"]["is_bot"] and by["DX1ABC-BOT"]["auto"] and by["DX1ABC-BOT"]["messages"] == 8, "DX1ABC-BOT is automatisch bot (8 berichten)")
check(not by["Alex"]["is_bot"] and by["Alex"]["manual"] is None, "Alex is geen bot")
check(not by["Botond"]["is_bot"], "Botond (mens) is geen bot")
check(by["Talbot"]["auto"], "Talbot wordt automatisch als bot gezien (bekende uitzondering)")
check(by["Echo Bot 2"]["is_bot"], "dubbele spaties in naam worden genormaliseerd")
check(by["Echobot"]["is_bot"] and by["Echobot"]["source"] == "contact" and by["Echobot"]["messages"] == 0, "Echobot komt uit de contacten (alleen advert)")
check("Gewone Companion" not in by, "gewone contacten (geen bot) staan er niet in")
check(OWN not in by, "eigen naam staat er niet in")
check("DmOnly" not in by, "DM-afzenders worden niet meegenomen")
check(XSS in by and by[XSS]["is_bot"], "naam met HTML komt ongewijzigd als data terug")
check([n["last_heard"] for n in data["names"]] == sorted([n["last_heard"] for n in data["names"]], reverse=True), "nieuwste eerst")
check(data["total"] == len(data["names"]) and data["bots"] == sum(n["is_bot"] for n in data["names"]), "tellers kloppen")

# 3. aanvinken
def setbot(name, val):
    return client.post("/api/bots/set", json={"name": name, "is_bot": val})
r = setbot("Alex", True); j = r.get_json()
check(r.status_code == 200 and j["is_bot"] and j["manual"] is True, "Alex aanvinken = handmatig bot")
r = setbot("Alex", False); j = r.get_json()
check(j["manual"] is None and not j["is_bot"], "Alex uitvinken = gelijk aan automatisch, dus geen uitzondering opgeslagen")
r = setbot("DX1ABC-BOT", False); j = r.get_json()
check(j["manual"] is False and not j["is_bot"], "DX1ABC-BOT uitvinken = handmatig geen bot")
r = setbot("DX1ABC-BOT", None); j = r.get_json()
check(j["manual"] is None and j["is_bot"], "terug naar automatisch")
r = setbot("Nieuwe Onbekende", True); j = r.get_json()
check(j["manual"] is True and j["source"] == "list", "nieuwe naam toevoegen als bot")
by = {n["name"]: n for n in client.get("/api/bots").get_json()["names"]}
check(by["Nieuwe Onbekende"]["is_bot"] and by["Nieuwe Onbekende"]["source"] == "list", "handmatig toegevoegde naam staat in de lijst")
setbot("talbot", False)
by = {n["name"]: n for n in client.get("/api/bots").get_json()["names"]}
check(by["Talbot"]["manual"] is False and not by["Talbot"]["is_bot"], "Talbot (hoofdletters anders) handmatig geen bot")

# 4. foute invoer
check(client.post("/api/bots/set", json={"name": "x", "is_bot": "ja"}).status_code == 400, "is_bot als tekst wordt geweigerd")
check(client.post("/api/bots/set", json={"is_bot": True}).status_code == 400, "ontbrekende naam wordt geweigerd")
check(client.post("/api/bots/set", json={"name": "   ", "is_bot": True}).status_code == 400, "lege naam wordt geweigerd")
check(client.post("/api/bots/set", json={"name": "x" * 41, "is_bot": True}).status_code == 400, "te lange naam wordt geweigerd")
check(client.post("/api/bots/set", data="geen json", content_type="text/plain").status_code == 400, "geen JSON wordt geweigerd")

# 5. de bot-kant ziet dezelfde lijsten
from modules.channel_hint import ChannelHint
bot_side = ChannelHint(types.SimpleNamespace(config=cfg, db_manager=viewer.db_manager, logger=viewer.logger))
check(bot_side.classify("Nieuwe Onbekende") == (True, "handmatig: bot"), "bot-kant: handmatige bot")
check(bot_side.classify("Talbot") == (False, "handmatig: geen bot"), "bot-kant: handmatig geen bot")
check(bot_side.classify("DX1ABC-BOT")[0], "bot-kant: automatische bot blijft bot")
# en de botlist-commando-kant schrijft in dezelfde opslag
bot_side.set_manual("Via Commando", True)
check(any(n["name"] == "Via Commando" and n["manual"] is True for n in client.get("/api/bots").get_json()["names"]), "wijziging via botlist is meteen zichtbaar op de pagina")

# 6. CSRF en inloggen
app.config["TESTING"] = False
r = client.post("/api/bots/set", json={"name": "Csrf Test", "is_bot": True})
check(r.status_code == 403, "POST zonder X-Requested-With wordt geweigerd (CSRF)")
r = client.post("/api/bots/set", json={"name": "Csrf Test", "is_bot": True}, headers={"X-Requested-With": "XMLHttpRequest"})
check(r.status_code == 200, "POST met X-Requested-With werkt")
app.config["TESTING"] = True

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
