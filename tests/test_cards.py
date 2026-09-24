"""De vier nieuwe kaarten op de echte (gepatchte) v1.1.0-viewer, met voorbeeldopties (fixtures/options_sample.json)."""
import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import configparser, copy, json, os, subprocess, sys, tempfile

TREE = sys.argv[1]
os.chdir(TREE); sys.path.insert(0, TREE)
GEN = ADDON + "/generate_config.py"
OLD_GEN = FIXTURES + "/generate_config_2.6.1.py"
FULL = json.load(open(FIXTURES + "/options_sample.json"))
FULL["webviewer"]["password"] = ""; FULL["webviewer"]["lan_access"] = True   # zoals live nu, en testbaar

work = tempfile.mkdtemp()
with open(f"{work}/options.json", "w") as f: json.dump(FULL, f)
subprocess.run([sys.executable, OLD_GEN, f"{work}/options.json", f"{work}/config.ini", work], check=True)   # zoals 2.6.1 hem schreef
_NEW = json.loads(json.dumps(FULL))
for _g in ("room_server", "notifications", "home_assistant", "webhook", "public_channel"): _NEW.pop(_g, None)
for _k in ("backup_enabled", "backup_time", "backup_keep", "cleanup_enabled", "cleanup_at", "cleanup_to", "cleanup_keep_days", "stale_enabled", "stale_repeater_days", "stale_other_days"): _NEW["contacts"].pop(_k, None)
json.dump(_NEW, open(f"{work}/options.json", "w"))
subprocess.run([sys.executable, GEN, f"{work}/options.json", f"{work}/config.ini", work], check=True)          # de update naar de nieuwe versie

from modules.web_viewer.app import BotDataViewer
from modules.settings_schema import validate_field, to_config_string
viewer = BotDataViewer(config_path=f"{work}/config.ini")
app = viewer.app; app.config["TESTING"] = True
client = app.test_client()

fails = []
def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

def cfg():
    c = configparser.ConfigParser(interpolation=None, strict=False); c.optionxform = str
    c.read(f"{work}/config.ini", encoding="utf-8"); return c

plugins = client.get("/api/plugins").get_json()["plugins"]
svc = {p["name"]: p for p in plugins if p["kind"] == "service"}
print("services op de Plugins-pagina:", sorted(svc))
WANT = {"notify": "Notifications", "contactcleanup": "ContactCleanup", "roomserverlogin": "RoomServer_Login",
        "homeassistantbridge": "HomeAssistantBridge"}
c = cfg()
for name, section in WANT.items():
    p = svc.get(name)
    check(p is not None and p["section"] == section, f"kaart '{name}' bestaat en hoort bij [{section}]")
    if not p: continue
    check(p["enabled"] == c.getboolean(section, "enabled"), f"[{section}] aan/uit-schakelaar toont de echte stand ({p['enabled']})")
    keys = {f["key"] for f in p["fields"]}
    in_cfg = set(c[section]) - {"enabled"}
    check(in_cfg <= keys, f"[{section}] alle sleutels uit config.ini staan op de kaart (mist: {sorted(in_cfg - keys)})")
    bad = []
    for f in p["fields"]:
        shown = f.get("value")
        raw = ", ".join(shown) if isinstance(shown, list) else shown
        ok, _, err = validate_field(f, raw if raw is not None else "")
        if not ok: bad.append(f"{f['key']}={raw!r}: {err}")
        if f["key"] in c[section] and f["type"] not in ("list", "password"):
            expect = c[section][f["key"]]
            if f["type"] == "bool": expect = expect.lower() == "true"
            elif f["type"] == "int": expect = int(expect)
            if shown != expect: bad.append(f"{f['key']}: toont {shown!r}, config heeft {expect!r}")
    check(not bad, f"[{section}] elke huidige waarde wordt goed getoond en door de validatie geaccepteerd" + (f" -> {bad}" if bad else ""))

# events-veld: precies de opgeslagen lijst
ev = next(f for f in svc["notify"]["fields"] if f["key"] == "events")
check(ev["value"] == [e.strip() for e in c["Notifications"]["events"].split(",")], "events-lijst komt overeen met config.ini")

# opslaan via de kaart
before_other = {s: dict(c[s]) for s in c.sections() if s not in ("Notifications",)}
body = {"section": "Notifications", "enabled": True,
        "values": {"destination": "room", "min_level": "WARNING", "cooldown_minutes": "45", "digest_seconds": "90",
                   "events": "startup, radio, error", "daily_summary": "false", "summary_time": "07:30",
                   "ha_notify": "true", "ha_notify_service": "notify.mobile_app_test", "target": ""}}
r = client.post("/api/plugins/service/notify", json=body)
check(r.status_code == 200 and r.get_json().get("success"), f"opslaan van de Meldingen-kaart lukt (HTTP {r.status_code})")
c2 = cfg()
n = c2["Notifications"]
check(n["min_level"] == "WARNING" and n["cooldown_minutes"] == "45" and n["digest_seconds"] == "90", "waarden staan in config.ini")
check(n["events"] == "startup, radio, error" and n["daily_summary"] == "false" and n["summary_time"] == "07:30", "lijst, schakelaar en tijd goed opgeslagen")
check(n["ha_notify_service"] == "notify.mobile_app_test", "tekstveld goed opgeslagen")
check({s: dict(c2[s]) for s in c2.sections() if s != "Notifications"} == before_other, "geen enkele andere sectie is veranderd door het opslaan")

# foute invoer wordt geweigerd
for label, key, val in (("ongeldige gebeurtenis", "events", "startup, bestaat-niet"), ("tijd", "summary_time", "25:99"),
                        ("negatief getal", "cooldown_minutes", "-5"), ("geen getal", "digest_seconds", "abc"),
                        ("onbekend niveau", "min_level", "INFO")):
    r = client.post("/api/plugins/service/notify", json={"section": "Notifications", "enabled": True, "values": {key: val}})
    check(r.status_code == 400 and not r.get_json()["success"], f"foute invoer wordt geweigerd: {label}")
check(cfg()["Notifications"]["cooldown_minutes"] == "45", "en een geweigerde invoer verandert niets")

# de overige drie kaarten opslaan
r = client.post("/api/plugins/service/contactcleanup", json={"section": "ContactCleanup", "enabled": True,
    "values": {"trigger_at": "320", "target": "260", "keep_days": "10", "stale_enabled": "true", "stale_repeater_days": "20", "stale_other_days": "40"}})
check(r.status_code == 200, "Contacten opschonen: opslaan lukt")
r = client.post("/api/plugins/service/roomserverlogin", json={"section": "RoomServer_Login", "enabled": True,
    "values": {"public_key": "ab" * 32, "password": "geheim!"}})
check(r.status_code == 200 and cfg()["RoomServer_Login"]["password"] == "geheim!", "Roomserver: sleutel en wachtwoord opslaan lukt")
r = client.post("/api/plugins/service/roomserverlogin", json={"section": "RoomServer_Login", "enabled": True, "values": {"public_key": "abc"}})
check(r.status_code == 400, "Roomserver: te korte sleutel wordt geweigerd")
r = client.post("/api/plugins/service/homeassistantbridge", json={"section": "HomeAssistantBridge", "enabled": True,
    "values": {"webhook_url": "http://127.0.0.1:8123/api/webhook/meshcore_bot_relay", "node_prefix": "5c6d7e"}})
check(r.status_code == 200 and cfg()["HomeAssistantBridge"]["node_prefix"] == "5c6d7e", "HA-koppeling: opslaan lukt")
r = client.post("/api/plugins/service/homeassistantbridge", json={"section": "HomeAssistantBridge", "enabled": True, "values": {"node_prefix": "xyz"}})
check(r.status_code == 400, "HA-koppeling: ongeldig voorvoegsel wordt geweigerd")


# ---- tweede helft van stap 1: kanaalhint, begroeting en webhook
c = cfg()
hint = svc.get("channelhint"); wh = svc.get("webhook")
cmds = {p["name"]: p for p in plugins if p["kind"] == "command"}
gr = cmds.get("greeter")
check(hint is not None and hint["section"] == "ChannelHint" and hint["enabled"] == c.getboolean("ChannelHint", "enabled"), "kaart 'channelhint' bestaat met de echte aan/uit-stand")
if hint:
    keys = {f["key"] for f in hint["fields"]}
    check(set(c["ChannelHint"]) - {"enabled"} <= keys, "kanaalhint: alle sleutels uit config.ini staan op de kaart")
    bad = []
    for f in hint["fields"]:
        sv = f.get("value"); raw = ", ".join(sv) if isinstance(sv, list) else sv
        ok, _, err = validate_field(f, raw if raw is not None else "")
        if not ok: bad.append(f"{f['key']}={raw!r}: {err}")
    check(not bad, "kanaalhint: elke huidige waarde wordt door de validatie geaccepteerd" + (f" -> {bad}" if bad else ""))
    fv = {f["key"]: f["value"] for f in hint["fields"]}
    check(fv.get("ignore_bot_commands") is True, "kanaalhint: 'niet reageren op andere bots' staat standaard aan")
    check(fv["channels"] == [x.strip() for x in c["ChannelHint"]["channels"].split(",")] and fv["where"] == [x.strip() for x in c["ChannelHint"]["where"].split(",")], "kanaalhint: kanalen en 'waar commando's werken' kloppen")
    check(fv["yield_seconds"] == int(c["ChannelHint"]["yield_seconds"]) and fv["cooldown_seconds"] == int(c["ChannelHint"]["cooldown_seconds"]), "kanaalhint: wachttijden kloppen")
    r = client.post("/api/plugins/service/channelhint", json={"section": "ChannelHint", "enabled": True, "values": {
        "channels": "Publiek, Extra", "where": "#bot, #test", "yield_seconds": "20", "cooldown_seconds": "90", "bot_words": "bot, robot"}})
    check(r.status_code == 200 and cfg()["ChannelHint"]["channels"] == "Publiek, Extra" and cfg()["ChannelHint"]["yield_seconds"] == "20", "kanaalhint opslaan lukt")
    for label, key, val in (("wachttijd te lang", "yield_seconds", "500"), ("cooldown te kort", "cooldown_seconds", "5"), ("geen getal", "yield_seconds", "x")):
        r = client.post("/api/plugins/service/channelhint", json={"section": "ChannelHint", "enabled": True, "values": {key: val}})
        check(r.status_code == 400, f"kanaalhint: foute invoer geweigerd ({label})")

check(gr is not None and gr["section"] == "Greeter_Command" and gr["enabled"] == c.getboolean("Greeter_Command", "enabled"), "begroeting-kaart bestaat met de echte aan/uit-stand")
if gr:
    gv = {f["key"]: f.get("value") for f in gr["fields"]}
    check(gv["greeting_message"] == c["Greeter_Command"]["greeting_message"] and gv["rollout_days"] == int(c["Greeter_Command"]["rollout_days"]), "begroeting: tekst en dagen kloppen")
    check(gv["channels"] in (["Publiek"], "Publiek"), f"begroeting: kanaal klopt ({gv['channels']!r})")
    extra = gr.get("values") or {}
    check("dead_air_delay_seconds" in extra and "defer_to_human_greeting" in extra, "begroeting: wachttijd en 'uitstellen aan een mens' staan in het vak met extra sleutels")
    r = client.post("/api/plugins/command/greeter", json={"section": "Greeter_Command", "enabled": True, "values": {"greeting_message": "Hallo @[{sender}], welkom!", "rollout_days": "3"}})
    g2 = cfg()["Greeter_Command"]
    check(r.status_code == 200 and g2["greeting_message"] == "Hallo @[{sender}], welkom!" and g2["rollout_days"] == "3", "begroeting opslaan lukt")
    check("dead_air_delay_seconds" in g2 and "defer_to_human_greeting" in g2 and g2["channels"] == c["Greeter_Command"]["channels"], "opslaan wist de extra sleutels en de kanalen niet")

check(wh is not None and wh["section"] == "Webhook" and wh["enabled"] == c.getboolean("Webhook", "enabled"), "webhook-kaart bestaat met de echte aan/uit-stand")
if wh:
    wv = {f["key"]: f.get("value") for f in wh["fields"]}
    check(wv["port"] == int(c["Webhook"]["port"]) and wv["max_message_length"] == int(c["Webhook"]["max_message_length"]) and wv["host"] == c["Webhook"]["host"], "webhook: poort, lengte en host kloppen")
    sf = next(f for f in wh["fields"] if f["key"] == "secret_token")
    check(sf["type"] == "password" and sf.get("has_value") is True and sf["value"] == "", "webhook: het geheim is een wachtwoordveld en wordt niet naar de browser gestuurd")
    r = client.post("/api/plugins/service/webhook", json={"section": "Webhook", "enabled": True, "values": {"max_message_length": "120"}})
    check(r.status_code == 200 and cfg()["Webhook"]["max_message_length"] == "120" and cfg()["Webhook"]["secret_token"] == c["Webhook"]["secret_token"], "webhook opslaan lukt en raakt het geheim niet")
    r = client.post("/api/plugins/service/webhook", json={"section": "Webhook", "enabled": True, "values": {"secret_token": "nieuw-geheim-123"}})
    check(r.status_code == 200 and cfg()["Webhook"]["secret_token"] == "nieuw-geheim-123", "webhook: een nieuw geheim intypen slaat het op")


# ---- stap 2 en 3: HARepeater en info bot
c = cfg()
hr = svc.get("harepeater"); info = cmds.get("info")
check(hr is not None and hr["section"] == "HARepeater" and hr["enabled"] is False, "kaart 'harepeater' bestaat en staat standaard UIT (alleen lezen, maar pas na jouw keuze)")
if hr:
    hv = {f["key"]: f["value"] for f in hr["fields"]}
    check(hv["repeaters"] == [] and hv["read_interval_minutes"] == 5 and hv["low_battery_notify"] is True and hv["low_battery_mv"] == 3600 and hv["keep_days"] == 365, "HARepeater: standaardwaarden (alles volgen, elke 5 min, alarm onder 3600 mV, 365 dagen)")
    bad = [f["key"] for f in hr["fields"] if not validate_field(f, ", ".join(f["value"]) if isinstance(f["value"], list) else f["value"])[0]]
    check(not bad, f"HARepeater: elke standaardwaarde wordt door de validatie geaccepteerd {bad}")
    r = client.post("/api/plugins/service/harepeater", json={"section": "HARepeater", "enabled": True, "values": {"repeaters": "a1b2c3d4e5", "read_interval_minutes": "10", "low_battery_mv": "3500", "keep_days": "90"}})
    h2 = cfg()["HARepeater"]
    check(r.status_code == 200 and h2["enabled"] == "true" and h2["repeaters"] == "a1b2c3d4e5" and h2["read_interval_minutes"] == "10" and h2["low_battery_mv"] == "3500", "HARepeater aanzetten en instellen via de kaart lukt")
    for label, key, val in (("prefix met rare tekens", "repeaters", "xyz"), ("interval 0", "read_interval_minutes", "0"), ("interval 61", "read_interval_minutes", "61"),
                            ("grens te laag", "low_battery_mv", "2000"), ("bewaartijd te kort", "keep_days", "3")):
        r = client.post("/api/plugins/service/harepeater", json={"section": "HARepeater", "enabled": True, "values": {key: val}})
        check(r.status_code == 400, f"HARepeater: foute invoer geweigerd ({label})")
if hr:
    hv = {f["key"]: f["value"] for f in hr["fields"]}
    check(hv["alert_reboot"] is True and hv["alert_offline"] is True and hv["alert_noise"] is True and hv["alert_airtime"] is True and hv["alert_neighbors"] is False
          and hv["noise_jump_db"] == 8 and hv["airtime_max_pct"] == 10, "HARepeater: waarschuwingen (herstart, offline, ruis, airtime aan; buur weg uit) met standaardgrenzen")
    r = client.post("/api/plugins/service/harepeater", json={"section": "HARepeater", "enabled": True, "values": {"alert_neighbors": True, "noise_jump_db": "12", "airtime_max_pct": "20", "alert_reboot": False}})
    h3 = cfg()["HARepeater"]
    check(r.status_code == 200 and h3["alert_neighbors"] == "true" and h3["noise_jump_db"] == "12" and h3["airtime_max_pct"] == "20" and h3["alert_reboot"] == "false", "HARepeater: waarschuwingen instellen via de kaart lukt")
    for label, key, val in (("ruissprong 2 dB", "noise_jump_db", "2"), ("ruissprong 41 dB", "noise_jump_db", "41"), ("airtime 0 %", "airtime_max_pct", "0"), ("airtime 101 %", "airtime_max_pct", "101")):
        r = client.post("/api/plugins/service/harepeater", json={"section": "HARepeater", "enabled": True, "values": {key: val}})
        check(r.status_code == 400, f"HARepeater: foute grens geweigerd ({label})")
    client.post("/api/plugins/service/harepeater", json={"section": "HARepeater", "enabled": True, "values": {"alert_reboot": True, "alert_neighbors": False, "noise_jump_db": "8", "airtime_max_pct": "10"}})
hb = svc.get("heartbeat")
check(hb is not None and hb["section"] == "Heartbeat" and hb["enabled"] is False, "kaart 'heartbeat' bestaat en staat standaard UIT")
if hb:
    bv = {f["key"]: f["value"] for f in hb["fields"]}
    check(bv["interval_minutes"] == 5 and bv["entity_id"] == "sensor.meshcore_bot_heartbeat", "Heartbeat: standaard elke 5 minuten, sensor.meshcore_bot_heartbeat")
    bad = [f["key"] for f in hb["fields"] if not validate_field(f, f["value"])[0]]
    check(not bad, f"Heartbeat: standaardwaarden geldig {bad}")
    r = client.post("/api/plugins/service/heartbeat", json={"section": "Heartbeat", "enabled": True, "values": {"interval_minutes": "10", "entity_id": "sensor.mijn_bot"}})
    b2 = cfg()["Heartbeat"]
    check(r.status_code == 200 and b2["enabled"] == "true" and b2["interval_minutes"] == "10" and b2["entity_id"] == "sensor.mijn_bot", "Heartbeat aanzetten en instellen via de kaart lukt")
    for label, key, val in (("interval 0", "interval_minutes", "0"), ("interval 31", "interval_minutes", "31"), ("geen sensor", "entity_id", "light.lamp"), ("hoofdletters", "entity_id", "sensor.Bot"), ("spatie", "entity_id", "sensor.mijn bot")):
        r = client.post("/api/plugins/service/heartbeat", json={"section": "Heartbeat", "enabled": True, "values": {key: val}})
        check(r.status_code == 400, f"Heartbeat: foute invoer geweigerd ({label})")
check(info is not None and info["section"] == "Info_Command", "kaart 'info' (commando 'info bot') bestaat")
if info:
    iv = {f["key"]: f["value"] for f in info["fields"]}
    check(iv["github_url"] == "" and iv["language"] == "nl" and iv["extra_line"] == "", "info: standaard zonder link, Nederlands, zonder eigen regel")
    r = client.post("/api/plugins/command/info", json={"section": "Info_Command", "enabled": True, "values": {"github_url": "https://github.com/voorbeeld/meshcore-ha-addons", "language": "en", "extra_line": "Run by Alex"}})
    i2 = cfg()["Info_Command"]
    check(r.status_code == 200 and i2["language"] == "en" and i2["github_url"].endswith("meshcore-ha-addons") and i2["extra_line"] == "Run by Alex", "info: link, taal en eigen regel opslaan lukt")
    r = client.post("/api/plugins/command/info", json={"section": "Info_Command", "enabled": True, "values": {"language": "xx"}})
    check(r.status_code == 400, "info: onbekende taal wordt geweigerd")
rp = cmds.get("rptr")
check(rp is not None and rp["section"] == "Rptr_Command", "commando 'rptr' staat op de Plugins-pagina")
ev = next(f for f in svc["notify"]["fields"] if f["key"] == "events")
check("repeater" in ev.get("pattern", "") and "repeater" in ev["value"] or "repeater" in ev.get("pattern", ""), "Meldingen-kaart kent de gebeurtenis 'repeater'")
r = client.post("/api/plugins/service/notify", json={"section": "Notifications", "enabled": True, "values": {"events": "startup, repeater, error"}})
check(r.status_code == 200 and "repeater" in cfg()["Notifications"]["events"], "de gebeurtenis 'repeater' kan op de kaart worden gekozen")


# ---- F1-kanaal
c = cfg()
f1s = svc.get("f1"); f1c = cmds.get("f1")
check(f1s is not None and f1s["section"] == "F1" and f1s["enabled"] is False, "kaart 'f1' bestaat en staat na de update UIT")
if f1s:
    fv = {f["key"]: f["value"] for f in f1s["fields"]}
    check(fv["channel"] == "#f1" and fv["daily_time"] == "12:00" and fv["reminder_minutes"] == 60 and fv["post_live"] is True and fv["live_milestones"] == [25, 50, 75]
          and fv["max_live_posts"] == 8 and fv["game_enabled"] is True and fv["timezone"] == "Europe/Amsterdam", "F1: standaardwaarden (kanaal #f1, 12:00, live aan, mijlpalen 25/50/75, spel aan)")
    bad = [f["key"] for f in f1s["fields"] if not validate_field(f, ", ".join(str(x) for x in f["value"]) if isinstance(f["value"], list) else f["value"])[0]]
    check(not bad, f"F1: elke standaardwaarde wordt door de validatie geaccepteerd {bad}")
    r = client.post("/api/plugins/service/f1", json={"section": "F1", "enabled": True, "values": {"daily_time": "13:30", "reminder_minutes": "30", "live_milestones": "20, 60",
                                                                                                  "max_live_posts": "5", "game_enabled": "false", "post_live": "false"}})
    h = cfg()["F1"]
    check(r.status_code == 200 and h["enabled"] == "true" and h["daily_time"] == "13:30" and h["live_milestones"] == "20, 60" and h["game_enabled"] == "false", "F1 aanzetten en instellen via de kaart lukt")
    for label, key, val in (("tijd 25:00", "daily_time", "25:00"), ("herinnering 500 min", "reminder_minutes", "500"), ("mijlpaal 150%", "live_milestones", "150"),
                            ("mijlpaal tekst", "live_milestones", "veel"), ("leesinterval 5 s", "live_read_seconds", "5"), ("max 0", "max_live_posts", "0")):
        r = client.post("/api/plugins/service/f1", json={"section": "F1", "enabled": True, "values": {key: val}})
        check(r.status_code == 400, f"F1: foute invoer geweigerd ({label})")
check(f1c is not None and f1c["section"] == "F1_Command", "commando 'f1' staat op de Plugins-pagina")
if f1c:
    cv = {f["key"]: f["value"] for f in f1c["fields"]}
    check(cv.get("channels") in (["#f1"], "#f1"), f"het f1-commando staat alleen in #f1 ({cv.get('channels')!r})")

# en de generator (herstart van de add-on) laat het allemaal staan
NEW = copy.deepcopy(FULL)
for g in ("room_server", "notifications", "home_assistant", "webhook", "public_channel"): NEW.pop(g, None)
for k in ("backup_enabled", "backup_time", "backup_keep", "cleanup_enabled", "cleanup_at", "cleanup_to", "cleanup_keep_days",
          "stale_enabled", "stale_repeater_days", "stale_other_days"): NEW["contacts"].pop(k, None)
with open(f"{work}/options.json", "w") as f: json.dump(NEW, f)
subprocess.run([sys.executable, GEN, f"{work}/options.json", f"{work}/config.ini", work], check=True)
c3 = cfg()
check(c3["Notifications"]["cooldown_minutes"] == "45" and c3["ContactCleanup"]["trigger_at"] == "320"
      and c3["RoomServer_Login"]["public_key"] == "ab" * 32 and c3["HomeAssistantBridge"]["node_prefix"] == "5c6d7e",
      "na een herstart (generator) staan alle kaartwijzigingen er nog")
check(c3["HARepeater"]["enabled"] == "true" and c3["HARepeater"]["repeaters"] == "a1b2c3d4e5" and c3["Info_Command"]["language"] == "en", "na een herstart staan ook de HARepeater- en info-instellingen er nog")
check(c3["Heartbeat"]["enabled"] == "true" and c3["Heartbeat"]["interval_minutes"] == "10" and c3["Heartbeat"]["entity_id"] == "sensor.mijn_bot", "na een herstart staan ook de Heartbeat-instellingen er nog")
check(c3["F1"]["enabled"] == "true" and c3["F1"]["daily_time"] == "13:30" and c3["F1"]["live_milestones"] == "20, 60", "na een herstart staan ook de F1-instellingen er nog")
check(c3["ChannelHint"]["yield_seconds"] == "20" and c3["Greeter_Command"]["rollout_days"] == "3" and c3["Webhook"]["max_message_length"] == "120"
      and c3["ChannelHint"]["channels"] == "Publiek, Extra", "na een herstart staan ook de kanaalhint-, begroeting- en webhookwijzigingen er nog")

print(f"\n{len(fails)} fouten"); sys.exit(1 if fails else 0)
