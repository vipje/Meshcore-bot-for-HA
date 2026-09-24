"""generate_config.py: verhuisde secties blijven van config.ini; de rest volgt de opties."""
import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import configparser, copy, json, os, sqlite3, subprocess, sys, tempfile

GEN = ADDON + "/generate_config.py"
OLD_GEN = FIXTURES + "/generate_config_2.6.1.py"      # generator zoals hij tot 2.6.1 was
FULL = json.load(open(FIXTURES + "/options_sample.json"))   # echte opties, 2.6.1
MOVED_GROUPS = ("room_server", "notifications", "home_assistant", "webhook", "public_channel")
MOVED_CONTACT_KEYS = ("backup_enabled", "backup_time", "backup_keep", "cleanup_enabled", "cleanup_at", "cleanup_to",
                      "cleanup_keep_days", "stale_enabled", "stale_repeater_days", "stale_other_days")
MOVED_SECTIONS = ("Notifications", "ContactCleanup", "RoomServer_Login", "HomeAssistantBridge", "Webhook", "ChannelHint", "Greeter_Command")
OLD_ONLY = MOVED_SECTIONS   # secties die de oude generator kende

NEW = copy.deepcopy(FULL)          # wat de Supervisor na de update nog bewaart
for g in MOVED_GROUPS: NEW.pop(g, None)
for k in MOVED_CONTACT_KEYS: NEW["contacts"].pop(k, None)

fails = []
def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

def run(gen, opts, d):
    with open(f"{d}/options.json", "w") as f: json.dump(opts, f)
    r = subprocess.run([sys.executable, gen, f"{d}/options.json", f"{d}/config.ini", d], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stderr

def read(d):
    c = configparser.ConfigParser(interpolation=None, strict=False); c.optionxform = str
    c.read(f"{d}/config.ini", encoding="utf-8"); return c

def sections(c, names): return {s: dict(c[s]) for s in names if c.has_section(s)}

def meta(d):
    conn = sqlite3.connect(f"{d}/meshcore_bot.db")
    try: return dict(conn.execute("SELECT key, value FROM bot_metadata").fetchall())
    finally: conn.close()

# ---- A. de huidige situatie: config.ini zoals 2.6.1 hem schreef
d = tempfile.mkdtemp(); run(OLD_GEN, FULL, d)
A = read(d)
moved_a = sections(A, MOVED_SECTIONS)
check(len(moved_a) == 7, "2.6.1 schreef alle zeven de verhuisde secties (ook Webhook, ChannelHint en Greeter_Command)")
check(moved_a["Notifications"]["cooldown_minutes"] == str(FULL["notifications"]["cooldown_minutes"]), "waarden komen uit de echte opties")
check(moved_a["RoomServer_Login"]["public_key"] == FULL["room_server"]["public_key"], "roomserver-sleutel uit de echte opties")

# ---- B. update naar 2.7.0 zonder dat er iets is gewijzigd: alles gelijk
run(GEN, NEW, d)
B = read(d)
check(sections(B, MOVED_SECTIONS) == moved_a, "verhuisde secties zijn na de update identiek (geen enkele waarde verloren)")
others = [s for s in A.sections() if s not in MOVED_SECTIONS]
def _strip(sec): return {k: v for k, v in sec.items() if not (k == "rate_limit_seconds")}
check({s: _strip(dict(A[s])) for s in others} == {s: _strip(dict(B[s])) for s in others}, "alle andere secties zijn ook identiek (alleen de nieuwe zendgrens-sleutel in [Bot] komt erbij)")
check(set(B.sections()) - set(A.sections()) == {"HARepeater", "F1", "F1_Command", "Heartbeat", "Localization", "AutoLanguage", "Reminders", "Community", "ChannelRadar"} and set(A.sections()) <= set(B.sections()), "alleen de nieuwe secties HARepeater, F1, F1_Command, Heartbeat, Localization, AutoLanguage, Reminders, Community en ChannelRadar komen erbij, geen enkele sectie is weg")
check(B["Reminders"]["enabled"] == "true" and B["Reminders"]["language"] == "nl" and B["Community"]["enabled"] == "true", "Reminders en Community staan na de update aan (anders werken herinner en dx/xp maar half)")
check(B["F1"]["enabled"] == "false" and B["F1"]["channel"] == "#f1" and B["F1_Command"]["channels"] == "#f1", "F1 staat na de update UIT; het f1-commando krijgt alleen #f1 als kanaal")
check("f1" not in B["Channels"]["monitor_channels"].lower(), "#f1 staat NIET bij de kanalen van de bot (zo werken ping, wx en de rest daar niet)")
check(B["Bot"]["rate_limit_seconds"] == "4", "zendgrens: zonder eigen optie wordt het standaard 4 seconden")
check(B["Heartbeat"]["enabled"] == "false" and B["Heartbeat"]["interval_minutes"] == "5" and B["Heartbeat"]["entity_id"] == "sensor.meshcore_bot_heartbeat", "Heartbeat staat na de update UIT, elke 5 minuten, standaard sensornaam")
check(B["Localization"]["language"] == "nl", "taal: standaard Nederlands")
check(B["HARepeater"]["enabled"] == "false" and B["HARepeater"]["read_interval_minutes"] == "5" and B["HARepeater"]["low_battery_mv"] == "3600", "HARepeater staat na de update UIT met de standaardwaarden")
check(B["AutoLanguage"]["enabled"] == "false", "AutoLanguage staat na de update UIT")

check(B.has_section("Greeter_Command") and B["Greeter_Command"]["greeting_message"] == FULL["public_channel"]["greeting"], "begroeting blijft staan, ook al genereert de nieuwe generator die sectie niet meer")
check(B["ChannelHint"]["channels"] == FULL["public_channel"]["channel"] and B["Webhook"]["secret_token"] == FULL["webhook"]["secret_token"], "kanaalhint- en webhookwaarden identiek")

# ---- C. wijzigingen op het dashboard overleven een herstart
c = read(d)
c["Notifications"]["cooldown_minutes"] = "45"
c["Notifications"]["events"] = "startup, error"
c["ContactCleanup"]["trigger_at"] = "310"
c["RoomServer_Login"]["password"] = "nieuw-wachtwoord"
c["HomeAssistantBridge"]["node_prefix"] = "abc123"
c["ChannelHint"]["yield_seconds"] = "20"
c["Greeter_Command"]["rollout_days"] = "3"
c["Webhook"]["max_message_length"] = "120"
del c["Notifications"]["ha_notify_service"]              # zelfs een gewiste sleutel wordt bij verse start weer aangevuld
with open(f"{d}/config.ini", "w") as f: c.write(f)
conn = sqlite3.connect(f"{d}/meshcore_bot.db"); conn.execute("UPDATE bot_metadata SET value='03:30' WHERE key='maint.db_backup_time'"); conn.commit(); conn.close()
# ook een niet-verhuisde wijziging op het dashboard (Plugins-pagina) blijft zoals voorheen behouden
c = read(d); c.add_section("Ping_Command") if not c.has_section("Ping_Command") else None
c["Ping_Command"]["channels"] = "#bot,#test"
with open(f"{d}/config.ini", "w") as f: c.write(f)
run(GEN, NEW, d); C = read(d)
check(C["Notifications"]["cooldown_minutes"] == "45" and C["Notifications"]["events"] == "startup, error", "Meldingen: dashboardwijziging overleeft herstart")
check(C["ContactCleanup"]["trigger_at"] == "310", "Contacten opschonen: wijziging overleeft")
check(C["RoomServer_Login"]["password"] == "nieuw-wachtwoord", "Roomserver-wachtwoord: wijziging overleeft")
check(C["HomeAssistantBridge"]["node_prefix"] == "abc123", "HA-koppeling: wijziging overleeft")
check(C["ChannelHint"]["yield_seconds"] == "20" and C["Greeter_Command"]["rollout_days"] == "3" and C["Webhook"]["max_message_length"] == "120", "kanaalhint, begroeting en webhook: dashboardwijzigingen overleven herstart")
check("ha_notify_service" in C["Notifications"], "een ontbrekende sleutel wordt aangevuld (standaardwaarde)")
check(meta(d)["maint.db_backup_time"] == "03:30", "back-uptijd van de Onderhoud-pagina wordt niet meer teruggezet")
check(C["Ping_Command"]["channels"] == "#bot,#test", "overige dashboardwijzigingen blijven behouden")
c = read(d); c["HARepeater"]["enabled"] = "true"; c["HARepeater"]["repeaters"] = "a1b2c3d4e5"
with open(f"{d}/config.ini", "w") as f: c.write(f)
c = read(d); c["F1"]["enabled"] = "true"; c["F1"]["daily_time"] = "13:30"; c["F1_Command"]["channels"] = "#f1, #bot"
with open(f"{d}/config.ini", "w") as f: c.write(f)
run(GEN, NEW, d)
check(read(d)["F1"]["enabled"] == "true" and read(d)["F1"]["daily_time"] == "13:30" and read(d)["F1_Command"]["channels"] == "#f1, #bot", "F1 aangezet en ingesteld op de kaart blijft na een herstart staan")
check(read(d)["HARepeater"]["enabled"] == "true" and read(d)["HARepeater"]["repeaters"] == "a1b2c3d4e5", "HARepeater aangezet op de kaart blijft aan na een herstart")

c = read(d); c["Heartbeat"]["enabled"] = "true"; c["Heartbeat"]["interval_minutes"] = "10"
with open(f"{d}/config.ini", "w") as f: c.write(f)
run(GEN, NEW, d)
check(read(d)["Heartbeat"]["enabled"] == "true" and read(d)["Heartbeat"]["interval_minutes"] == "10", "Heartbeat aangezet op de kaart blijft aan na een herstart")

# ---- D. niet-verhuisde opties blijven de bron: wijziging in HA-opties komt nog steeds door
opts2 = copy.deepcopy(NEW); opts2["bot"]["tx_delay_seconds"] = 5.0; opts2["contacts"]["protect_starred"] = False; opts2["bot"]["rate_limit_seconds"] = 6
run(GEN, opts2, d); D = read(d)
check(D["Bot"]["rate_limit_seconds"] == "6", "zendgrens: de HA-optie werkt")
check(D["Bot"]["bot_tx_rate_limit_seconds"] == "5.0" and D["Bot"]["protect_starred"] == "false", "niet-verhuisde HA-opties werken nog")
opts3 = copy.deepcopy(opts2); opts3["bot"]["language"] = "en"
run(GEN, opts3, d); check(read(d)["Localization"]["language"] == "en", "taal: de HA-optie language werkt (en)")
run(GEN, opts2, d)
check(D["Notifications"]["cooldown_minutes"] == "45", "en raken de verhuisde waarden niet")

# ---- E. verse installatie: standaardwaarden voor alles wat verhuisd is
d2 = tempfile.mkdtemp(); minimal = {"connection": {"type": "tcp"}, "bot": {"name": "X", "channels": ["test"]}}
run(GEN, minimal, d2); E = read(d2)
check(all(E.has_section(s) for s in MOVED_SECTIONS if s != "Greeter_Command"), "verse installatie: alle verhuisde secties bestaan (behalve de begroeting: upstream-standaard is uit)")
check(E["Notifications"]["enabled"] == "false" and E["Notifications"]["destination"] == "room" and E["Notifications"]["cooldown_minutes"] == "30", "Meldingen: standaardwaarden (uit)")
check(E["ContactCleanup"]["enabled"] == "false" and E["ContactCleanup"]["trigger_at"] == "300" and E["ContactCleanup"]["target"] == "250", "Opschonen: standaardwaarden (uit)")
check(E["RoomServer_Login"]["enabled"] == "false" and E["HomeAssistantBridge"]["enabled"] == "false", "Roomserver en HA-koppeling standaard uit")
m = meta(d2)
check(m["maint.db_backup_enabled"] == "true" and m["maint.db_backup_time"] == "02:00" and m["maint.db_backup_retention_count"] == "7", "verse installatie: dagelijkse back-up 02:00, 7 bewaren")

check(E["HARepeater"]["enabled"] == "false" and E["F1"]["enabled"] == "false" and E["F1_Command"]["channels"] == "#f1", "verse installatie: HARepeater en F1 uit, f1-commando alleen in #f1")
check(E["AutoLanguage"]["enabled"] == "false", "verse installatie: AutoLanguage uit")
check(E["Webhook"]["enabled"] == "false", "verse installatie: webhook staat UIT (geen open poort zonder geheim)")
check(E["ChannelHint"]["enabled"] == "false" and E["ChannelHint"]["channels"] == "", "verse installatie: kanaalhint uit en zonder kanalen")
check(not E.has_section("Greeter_Command") and not E.has_section("Scheduled_Messages"), "verse installatie: geen begroeting en geen geplande berichten")

# ---- G. een eerder actieve aankondiging (Scheduled_Messages) wordt nooit gewist
d3 = tempfile.mkdtemp(); opts_ann = copy.deepcopy(FULL); opts_ann["public_channel"]["announcement_enabled"] = True
opts_ann["public_channel"]["announcement_channels"] = ["#bot = commando's", "#test = testen"]
run(OLD_GEN, opts_ann, d3); GA = read(d3)
check(GA.has_section("Scheduled_Messages") and len(GA["Scheduled_Messages"]) >= 1, "voorwaarde: oude generator maakte een aankondigingsschema")
before_sched = dict(GA["Scheduled_Messages"])
run(GEN, NEW, d3)
check(read(d3).has_section("Scheduled_Messages") and dict(read(d3)["Scheduled_Messages"]) == before_sched, "bestaand aankondigingsschema blijft na de update staan")

# ---- F. een herstart draait de generator opnieuw: niets verandert
before = sections(read(d), read(d).sections())
run(GEN, opts2, d)
check(sections(read(d), read(d).sections()) == before, "tweede run zonder wijzigingen verandert niets")

print(f"\n{len(fails)} fouten"); sys.exit(1 if fails else 0)
