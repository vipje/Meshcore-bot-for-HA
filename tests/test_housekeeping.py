"""Housekeeping of 2.14.5 against the real patched upstream code: the room-server re-login interval (card setting),
no "unknown key" warnings for the add-on's own keys, and the contact-capacity cleanup that no longer repeats a round
that cannot remove anything."""
import asyncio
import configparser
import logging
import os
import pathlib as _pl
import sys
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
    global RoomServerLoginService, RepeaterManager, validate_config_keys, clock_action, EventType
    from modules.service_plugins.room_server_login_service import RoomServerLoginService, clock_action
    from meshcore import EventType
    from modules.repeater_manager import RepeaterManager
    from modules.config_schema import validate_config_keys


import_with_stubs(_imp)

fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def bot_with(section_values):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "X"}
    cfg["RoomServer_Login"] = {"enabled": "true", "public_key": "ab" * 32, "password": "x", **section_values}
    return types.SimpleNamespace(config=cfg, logger=logging.getLogger("hk"))


# ---------------------------------------------------------------- room server re-login interval
check(RoomServerLoginService(bot_with({})).relogin_seconds == 3600, "room server: standaard elk uur opnieuw inloggen")
check(RoomServerLoginService(bot_with({"relogin_minutes": "180"})).relogin_seconds == 180 * 60, "room server: interval van de kaart (180 min)")
check(RoomServerLoginService(bot_with({"relogin_minutes": "5"})).relogin_seconds == 15 * 60
      and RoomServerLoginService(bot_with({"relogin_minutes": "9999"})).relogin_seconds == 720 * 60
      and RoomServerLoginService(bot_with({"relogin_minutes": "abc"})).relogin_seconds == 3600,
      "room server: interval begrensd op 15..720 min, onzin = standaard")
field = [f for f in RoomServerLoginService.settings_schema if f["key"] == "relogin_minutes"]
check(field and field[0]["default"] == 60 and field[0]["min"] == 15 and field[0]["max"] == 720, "room server: kaartveld 'Log in again every' (60, 15..720)")

# ---------------------------------------------------------------- the room's clock
NOW = 1_790_000_000
check(clock_action(NOW - 30, NOW, True) == ("ok", 30), "klok: 30 s verschil is goed")
check(clock_action(NOW - 3 * 86400, NOW, True) == ("sync", 3 * 86400), "klok: 3 dagen achter + beheerder = clock sync")
check(clock_action(NOW - 3 * 86400, NOW, False) == ("behind", 3 * 86400), "klok: achter als gast = alleen melden")
check(clock_action(NOW + 3600, NOW, True) == ("ahead", -3600), "klok: vóór = alleen melden (clock sync zet niet terug)")
check(clock_action(None, NOW, True) == ("sync", None) and clock_action(None, NOW, False) == ("unknown", None),
      "klok: room stuurt geen tijd mee = beheerder synct voor de zekerheid, gast doet niets")


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, r):
        self.lines.append((r.levelname, r.getMessage()))


def fake_room(server_ts, is_admin, admin_pw=""):
    sent = {"login": None, "cmds": []}

    async def send_login_sync(key, pwd, **kw):
        sent["login"] = pwd
        payload = {"is_admin": is_admin, "permissions": 1 if is_admin else 0}
        if server_ts is not None:
            payload["server_timestamp"] = server_ts
        return types.SimpleNamespace(type=EventType.LOGIN_SUCCESS, payload=payload)

    async def send_cmd(dst, cmd, timestamp=None, dst_type=None):
        sent["cmds"].append((dst, cmd, dst_type))
        return types.SimpleNamespace(type="MSG_SENT")
    b = bot_with({"admin_password": admin_pw} if admin_pw else {})
    b.logger = logging.getLogger(f"room{len(admin_pw)}{is_admin}{server_ts}")
    cap = Capture()
    b.logger.handlers = [cap]
    b.logger.setLevel(logging.DEBUG)
    b.meshcore = types.SimpleNamespace(commands=types.SimpleNamespace(send_login_sync=send_login_sync, send_cmd=send_cmd))
    return RoomServerLoginService(b), sent, cap


async def clock_cases():
    now = time.time()
    svc, sent, cap = fake_room(int(now - 2 * 86400), True, admin_pw="geheim-admin")
    await svc._login_once()
    check(sent["login"] == "geheim-admin" and sent["cmds"] == [("ab" * 32, "clock sync", 3)],
          f"beheerder, room 2 dagen achter: inloggen met het admin-wachtwoord en 'clock sync' naar de room ({sent})")
    check(any("liep 2 dag(en) achter" in m for _l, m in cap.lines), "beheerder: in het logboek staat hoeveel de klok achterliep")
    svc, sent, cap = fake_room(int(now - 2 * 86400), False)
    await svc._login_once()
    check(sent["login"] == "x" and sent["cmds"] == [] and any(l == "WARNING" and "admin-wachtwoord" in m for l, m in cap.lines),
          "gast, room achter: geen clock sync, wel een waarschuwing met de tip")
    svc, sent, cap = fake_room(int(now - 10), True, admin_pw="a")
    await svc._login_once()
    check(sent["cmds"] == [], "klok klopt: niets gestuurd")
    svc, sent, cap = fake_room(int(now + 7200), True, admin_pw="a")
    await svc._login_once()
    check(sent["cmds"] == [] and any("vóór" in m for _l, m in cap.lines), "room loopt vóór: geen clock sync, wel gemeld")
    b = bot_with({"clock_sync": "false", "admin_password": "a"})
    svc, sent, cap = fake_room(int(now - 86400), True, admin_pw="a")
    svc.clock_sync = RoomServerLoginService(b).clock_sync
    await svc._login_once()
    check(svc.clock_sync is False and sent["cmds"] == [], "schakelaar 'Keep the room's clock right' uit: niets gestuurd")
    keys = {f["key"]: f for f in RoomServerLoginService.settings_schema}
    check(keys["admin_password"]["type"] == "password" and keys["clock_sync"]["default"] is True,
          "kaart: admin-wachtwoord als wachtwoordveld, klok bijhouden standaard aan")


asyncio.run(clock_cases())

# ---------------------------------------------------------------- no "unknown key" warnings for our own keys
cfg = configparser.ConfigParser()
cfg["Bot"] = {"bot_name": "X", "protect_starred": "true", "keep_radio_favourites": "true", "made_up_key": "1"}
cfg["Feed_Manager"] = {"default_max_item_age_minutes": "30"}
cfg["Help_Command"] = {"list_url": "https://example.org/commands"}
warnings = [m for _s, m in validate_config_keys(cfg) if "unknown key" in m]
ours = [m for m in warnings if any(k in m for k in ("protect_starred", "keep_radio_favourites", "default_max_item_age_minutes", "list_url"))]
check(not ours, f"geen 'unknown key'-waarschuwing meer voor onze eigen sleutels {ours}")
check(any("made_up_key" in m for m in warnings), "een echte tikfout wordt nog steeds gemeld (de controle werkt nog)")

# ---------------------------------------------------------------- contact capacity cleanup does not repeat a no-op round
calls = {"status": 0, "purge": 0, "aggressive": 0}
removable = {"n": 0}


async def get_status():
    calls["status"] += 1
    return {"is_near_limit": True, "is_at_limit": True, "usage_percentage": 100.0, "current_contacts": 350,
            "estimated_limit": 350, "stale_contacts": [], "repeater_count": 20}


async def remove_stale(stale):
    return 0


async def purge_old(days_old=14, reason=""):
    calls["purge"] += 1
    return 0


async def aggressive():
    calls["aggressive"] += 1
    return removable["n"]


fake = types.SimpleNamespace(get_contact_list_status=get_status, _remove_stale_contacts=remove_stale, purge_old_repeaters=purge_old,
                             _aggressive_contact_cleanup=aggressive, log_purging_action=lambda *a, **k: None, logger=logging.getLogger("rm"))


async def main():
    r1 = await RepeaterManager.manage_contact_list(fake, auto_cleanup=True)
    r2 = await RepeaterManager.manage_contact_list(fake, auto_cleanup=True)
    check(r1["success"] and calls["status"] == 1 and r2.get("skipped"), "volle lijst, niets te verwijderen: de volgende ronde wordt overgeslagen")
    fake._capacity_quiet_until = time.time() - 1          # 6 hours later
    removable["n"] = 5
    r3 = await RepeaterManager.manage_contact_list(fake, auto_cleanup=True)
    check(calls["status"] == 2 and r3["actions_taken"] == ["Aggressive cleanup removed 5 contacts"] and fake._capacity_quiet_until == 0.0,
          "na 6 uur weer een ronde; iets verwijderd = geen pauze")
    r4 = await RepeaterManager.manage_contact_list(fake, auto_cleanup=True)
    check(calls["status"] == 3 and not r4.get("skipped"), "na een ronde die wel iets opruimde gaat de volgende gewoon door")
    fake._capacity_quiet_until = time.time() + 3600
    await RepeaterManager.manage_contact_list(fake, auto_cleanup=False)
    check(calls["status"] == 4, "een handmatige controle (auto_cleanup uit) wordt nooit overgeslagen")


asyncio.run(main())

# ---------------------------------------------------------------- the image stays below Docker's layer limit
DOCKERFILE = _pl.Path(__file__).resolve().parent.parent / "meshcore-bot" / "Dockerfile"
steps = [l for l in DOCKERFILE.read_text().splitlines() if l.startswith(("COPY ", "RUN ", "ADD "))]
check(len(steps) <= 30, f"Dockerfile: {len(steps)} lagen (Docker stopt bij 127 met 'max depth exceeded'; grens hier 30)")
addon = DOCKERFILE.parent
listed = [l.strip() for l in (addon / "local_patches" / "ORDER").read_text().splitlines() if l.strip() and not l.strip().startswith("#")]
present = sorted(p.name for p in (addon / "local_patches").glob("patch_*.py"))
check(sorted(listed) == present and len(set(listed)) == len(listed), "local_patches/ORDER noemt elke patch precies één keer")
check("**/__pycache__" in (addon / ".dockerignore").read_text(), ".dockerignore houdt __pycache__ buiten het image")
print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
