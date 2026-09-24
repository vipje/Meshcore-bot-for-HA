"""rptr, info bot en de batterijmelding via de meldingsservice, tegen de echte gepatchte upstream-klassen."""
import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import asyncio, configparser, importlib.util, logging, os, sys, time, types
from unittest.mock import MagicMock
TREE = sys.argv[1]; os.chdir(TREE); sys.path.insert(0, TREE)
sys.path.insert(0, FIXTURES)
import ha_states as F

def import_with_stubs(fn):
    for _ in range(40):
        try: return fn()
        except ModuleNotFoundError as e:
            if e.name.split(".")[0] == "modules": raise
            sys.modules[e.name] = MagicMock(); sys.modules.setdefault(e.name.split(".")[0], MagicMock())
    raise SystemExit("te veel ontbrekende modules")

def _imp():
    global MeshMessage, RptrCommand, InfoCommand, HARepeaterService, parse_states, info_mod, Translator
    from modules.models import MeshMessage
    from modules.commands.rptr_command import RptrCommand
    from modules.commands import info_command as info_mod
    from modules.commands.info_command import InfoCommand
    from modules.service_plugins.ha_repeater_service import HARepeaterService
    from modules.ha_repeater_parser import parse_states
    from modules.i18n import Translator
import_with_stubs(_imp)

def nl_translator():
    return Translator("nl", "translations/", "local/translations")

fails = []
def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c: fails.append(m)

NOW = time.time()
def cfg(**sections):
    c = configparser.ConfigParser(interpolation=None)
    c["Bot"] = {"bot_name": "Own|🤖"}
    for k, v in sections.items(): c[k] = v
    return c

def make_bot(config=None, service=None):
    return types.SimpleNamespace(config=config or cfg(), logger=logging.getLogger("t"), services=({"harepeater": service} if service else {}), command_manager=types.SimpleNamespace(monitor_channels=["#bot", "#test"]), translator=nl_translator())

def make_service(states, last_read=None, wanted=None, last_error=""):
    b = types.SimpleNamespace(config=cfg(HARepeater={"enabled": "true", "repeaters": ",".join(wanted or [])}), logger=logging.getLogger("t"), db_manager=None)
    s = HARepeaterService(b)
    s.repeaters = parse_states(states, now=NOW); s.last_read = NOW if last_read is None else last_read; s.last_error = last_error
    return s

async def run(cmd_cls, text, bot, is_dm=True):
    cmd = cmd_cls(bot); out = []
    async def send_response(message, content, **kw): out.append(content); return True
    async def send_response_chunked(message, chunks, **kw): out.extend(chunks); return True
    cmd.send_response, cmd.send_response_chunked = send_response, send_response_chunked
    await cmd.execute(MeshMessage(content=text, sender_id="Alex", is_dm=is_dm))
    return out

ST = F.repeater_states(NOW) + F.room_states(NOW)

async def main():
    svc = make_service(ST)
    bot = make_bot(service=svc)
    # ---------------- rptr
    r = await run(RptrCommand, "rptr", bot)
    print("   ", r)
    check(len(r) == 1 and r[0].startswith("NL|XX|TOWN|RPTR|01: 3,92 V (78%) | up 12d 19u | airtime 1,9% | 3 buren") and len(r[0].encode()) <= 130, "rptr: één regel met batterij, uptime, airtime en buren")
    r = await run(RptrCommand, "!rptr buren", bot); print("   ", r)
    check(len(r) == 1 and "BE-Nabij 12,0 dB" in r[0] and len(r[0].encode()) <= 130, "rptr buren: sterkste buur eerst")
    r = await run(RptrCommand, "rptr list", bot); print("   ", r)
    check(any("a1b2c3d4e5" in x for x in r) and any("f6e5d4c3b2" in x and "niet gevolgd" in x for x in r), "rptr list: alle bekende apparaten, room server als 'niet gevolgd'")
    r = await run(RptrCommand, "rptr town", bot); check(len(r) == 1 and r[0].startswith("NL|XX"), "rptr <naam> kiest die repeater")
    r = await run(RptrCommand, "rptr bestaat-niet", bot); check("geen repeater gevonden" in r[0] and "rptr list" in r[0], "onbekende naam: nette melding")
    r = await run(RptrCommand, "rptr", make_bot()); check("staat uit" in r[0] and "HARepeater" in r[0], "service niet geladen: uitleg wat te doen")
    r = await run(RptrCommand, "rptr", make_bot(service=make_service(ST, last_read=0.0, last_error="HARepeater: geen toegang"))); check("nog geen gegevens" in r[0] and "geen toegang" in r[0], "nog niet gelezen: melding met de laatste fout")
    r = await run(RptrCommand, "rptr", make_bot(service=make_service([]))); check("geen repeater gevonden" in r[0], "Home Assistant kent geen repeaters: melding")
    stale = F.repeater_states(NOW, age=5 * 3600) + F.room_states(NOW)
    r = await run(RptrCommand, "rptr", make_bot(service=make_service(stale))); check("LET OP: 5 u oud" in r[0], "oude gegevens: LET OP")
    two = ST + [dict(x, entity_id=x["entity_id"].replace(F.PFX, "bbbbbbbbbb").replace(F.SLUG, "tweede_rptr")) for x in F.repeater_states(NOW)[:3]]
    for x in two[-3:]: x["attributes"] = dict(x["attributes"], friendly_name="MeshCore Repeater: Tweede RPTR (bbbbbb) Battery")
    r = await run(RptrCommand, "rptr", make_bot(service=make_service(two))); print("   ", r)
    check(len(r) == 2 and all(len(x.encode()) <= 130 for x in r), "twee repeaters: twee regels, elk binnen de lengte")
    r = await run(RptrCommand, "rptr", make_bot(service=make_service(ST, wanted=["f6e5d4"]))); check(r[0].startswith("Home Room:"), "kaart met prefix van een room server: die wordt gevolgd")
    long_name = [dict(x) for x in ST]
    for x in long_name:
        if x["entity_id"].endswith(F.SLUG): x["attributes"] = dict(x["attributes"], friendly_name="MeshCore Repeater: " + "X" * 90 + " (a1b2c3) Battery")
    r = await run(RptrCommand, "rptr", make_bot(service=make_service(long_name))); check(len(r[0].encode()) <= 130, "hele lange naam: het bericht blijft binnen de lengte")

    # ---------------- info bot
    nl = info_mod.build_messages("nl", "", "")
    print("   ", nl)
    check(len(nl) == 2 and all(len(m.encode()) <= 130 for m in nl), "info bot zonder link: 2 berichten binnen 130 bytes")
    check("github" not in " ".join(nl).lower().replace("agessaman", "") and "Meer info" not in " ".join(nl), "zonder link staat er geen link-stuk in")
    url = "https://github.com/voorbeeld/meshcore-ha-addons"
    withurl = info_mod.build_messages("nl", url, "Beheerd door Alex"); print("   ", withurl)
    check(len(withurl) <= 3 and all(len(m.encode()) <= 130 for m in withurl) and url in " ".join(withurl) and "Beheerd door Alex" in " ".join(withurl), "met link en eigen regel: max 3 berichten, alles erin")
    en = info_mod.build_messages("en", url, ""); check("Home Assistant add-on" in en[0] and url in " ".join(en), "Engelse tekst")
    de = info_mod.build_messages("de", "", ""); check(de[0].startswith("Ich bin ein MeshCore-Bot"), "Duitse tekst")
    fr = info_mod.build_messages("fr", "", ""); check(fr[0].startswith("Je suis un bot MeshCore"), "Franse tekst")
    check(info_mod.build_messages("es", "", "") == nl and info_mod.build_messages("", "", "") == nl, "onbekende of lege taal valt terug op Nederlands")
    check(all(len(m.encode()) <= 130 for m in info_mod.build_messages("nl", "https://x.example/" + "a" * 300, "b" * 400)), "absurd lange link en regel: nog steeds binnen de lengte")
    check(len(info_mod.build_messages("nl", "", "b" * 400)) <= 3, "nooit meer dan 3 berichten")
    icmd = InfoCommand(make_bot(cfg(Info_Command={"github_url": url, "language": "en", "extra_line": "Run by Alex"})))
    dm = MeshMessage(content="info bot", sender_id="V", is_dm=True); ch = MeshMessage(content="info bot", sender_id="V", is_dm=False, channel="#bot")
    check(icmd.requires_dm and icmd.matches_keyword(dm) and icmd.matches_keyword(MeshMessage(content="infobot", sender_id="V", is_dm=True)), "trefwoorden 'info bot' en 'infobot'")
    check(not icmd.matches_keyword(MeshMessage(content="info", sender_id="V", is_dm=True)) and not icmd.matches_keyword(MeshMessage(content="info botx", sender_id="V", is_dm=True)), "'info' of 'info botx' matcht niet")
    check(icmd.can_execute(dm) is True and icmd.can_execute(ch) is False, "alleen via DM, niet in een kanaal")
    out = await run(InfoCommand, "info bot", make_bot(cfg(Info_Command={"github_url": url, "language": "en", "extra_line": "Run by Alex"})))
    check(url in " ".join(out) and "Run by Alex" in " ".join(out) and out[0].startswith("I am a MeshCore bot"), "uitvoeren gebruikt de instellingen van de kaart")
    out = await run(InfoCommand, "info bot", make_bot()); check(len(out) == 2 and out[0].startswith("Ik ben een MeshCore-bot"), "zonder instellingen: Nederlands, zonder link")
    check(icmd.get_config_value("Info_Command", "enabled", fallback=True, value_type="bool") is True, "staat standaard aan")

    # ---------------- batterijmelding via de meldingsservice
    pkg = types.ModuleType("fakepkg"); pkg.__path__ = []; sys.modules["fakepkg"] = pkg
    base = types.ModuleType("fakepkg.base_service")
    class BaseServicePlugin:
        def __init__(self, bot): self.bot = bot; self.logger = bot.logger
    base.BaseServicePlugin = BaseServicePlugin; sys.modules["fakepkg.base_service"] = base
    spec = importlib.util.spec_from_file_location("fakepkg.notify_service", ADDON + "/local_service_plugins/notify_service.py")
    ns = importlib.util.module_from_spec(spec); spec.loader.exec_module(ns)
    def notifier(events, low_notify):
        c = cfg(Notifications={"enabled": "true", "events": events, "cooldown_minutes": "30"}, HARepeater={"enabled": str(low_notify).lower()})
        b = types.SimpleNamespace(config=c, logger=logging.getLogger("n"), connected=False)
        n = ns.NotifyService(b); return n
    line = "HARepeater: batterij laag: NL|XX|TOWN|RPTR|01 3.50 V (78%) (grens 3.60 V)"
    n = notifier("startup, error", True); n._ingest(logging.WARNING, line, time.time())
    check(n._queue.qsize() == 1, "lijst zonder 'repeater' maar kaart aan: batterijmelding gaat toch door")
    cat, text = n._queue.get_nowait(); print("   ", cat, "|", text)
    check(cat == "repeater" and text.startswith("batterij laag: NL|XX|TOWN|RPTR|01 3.50 V") and "HARepeater:" not in text, "melding zonder technisch voorvoegsel")
    check(cat not in ns.INFO_CATEGORIES, "telt als waarschuwing (⚠), niet als info")
    n = notifier("startup, error", False); n._ingest(logging.WARNING, line, time.time()); check(n._queue.qsize() == 0, "kaart uit én niet in de lijst: geen melding")
    n = notifier("startup, repeater", False); n._ingest(logging.WARNING, line, time.time()); check(n._queue.qsize() == 1, "staat 'repeater' in de lijst: melding, ook met kaart uit")
    n = notifier("startup, error", True); t0 = time.time(); n._ingest(logging.WARNING, line, t0); n._ingest(logging.WARNING, line.replace("3.50", "3.49"), t0 + 3600)
    check(n._queue.qsize() == 1, "dezelfde repeater binnen 24 uur: maar één melding")
    n2 = notifier("startup, error", True); n2.notify_enabled = False; n2._ingest(logging.WARNING, line, time.time()); check(n2._queue.qsize() == 0, "meldingen uit: niets")
    for what, sample in [("herstart", "HARepeater: herstart: NL|XX|TOWN|RPTR|01 zojuist herstart (uptime 4 min)"),
                         ("offline", "HARepeater: offline: NL|XX|TOWN|RPTR|01 al 3 uur geen gegevens"),
                         ("ruisvloer hoog", "HARepeater: ruisvloer hoog: NL|XX|TOWN|RPTR|01 -95 dBm (+12 dB)"),
                         ("airtime hoog", "HARepeater: airtime hoog: NL|XX|TOWN|RPTR|01 14 %"),
                         ("buur weg", "HARepeater: buur weg: NL|XX|TOWN|RPTR|01 buur ABC123 niet meer gezien")]:
        n = notifier("startup, error", True); n._ingest(logging.WARNING, sample, time.time())
        got = n._queue.get_nowait() if n._queue.qsize() == 1 else None
        check(got is not None and got[0] == "repeater" and got[1].startswith(what) and "HARepeater:" not in got[1], f"melding '{what}' komt door als repeater-waarschuwing")
    msgs = ns.build_messages([text], [])
    check(msgs and msgs[0].startswith("⚠ batterij laag") and all(len(m.encode()) <= 140 for m in msgs), "uiteindelijk bericht past en begint met ⚠")

    print(f"\n{len(fails)} fouten"); sys.exit(1 if fails else 0)

asyncio.run(main())
