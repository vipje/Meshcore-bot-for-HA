import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import configparser, sys, types
sys.path.insert(0, ADDON + "/local_shared")
from channel_hint import ChannelHint

def cfg(**kw):
    c = configparser.ConfigParser(); c["Bot"] = {"bot_name": "Own|🤖"}
    c["ChannelHint"] = {"enabled": "true", "channels": "Publiek", "where": "#test", "yield_seconds": "15", **kw}
    return c

bot = types.SimpleNamespace(config=cfg(), db_manager=types.SimpleNamespace(get_metadata=lambda k: None, set_metadata=lambda k, v: None), logger=None)
h = ChannelHint(bot)
msg = lambda ch: types.SimpleNamespace(channel=ch, is_dm=False)
ok = lambda c, m: print(("OK   " if c else "FAIL ") + m) or (c or sys.exit(1))
ok(h.is_hint_channel(msg("Publiek")) and not h.is_hint_channel(msg("Extra")), "start: alleen Publiek is een hintkanaal")
h._bot_seen["publiek"] = 123.0
bot.config = cfg(channels="Publiek, Extra", yield_seconds="0", bot_words="robot")    # bot laadt na een dashboard-opslag een nieuwe config
ok(not h.is_hint_channel(msg("Extra")) and h.yield_seconds == 15, "binnen 30 s nog de oude waarden (geen onnodig herlezen)")
h._settings_at -= 31
ok(h.is_hint_channel(msg("Extra")) and h.yield_seconds == 0, "na 30 s: nieuw kanaal en nieuwe wachttijd actief zonder herstart")
ok(h._bot_seen == {"publiek": 123.0}, "opgebouwde toestand (welke bot waar sprak) blijft behouden")
ok(h.classify_auto("Robot Fan")[0] and not h.classify_auto("DX1ABC-BOT")[0], "ook de botwoorden volgen de nieuwe config")
bot.config = None; h._settings_at -= 31                                              # kapotte config: laatste goede waarden blijven
ok(h.is_hint_channel(msg("Extra")), "een onleesbare config laat de laatste goede instellingen staan en crasht niet")
ok(h.ignore_bot_commands is True, "'niet reageren op andere bots' staat standaard aan (ook zonder sleutel in de config)")
bot.config = cfg(ignore_bot_commands="false"); h._settings_at -= 31; h._refresh_settings()
ok(h.ignore_bot_commands is False, "uitzetten op de kaart werkt binnen 30 s zonder herstart")
bot.config = configparser.ConfigParser(); bot.config["Bot"] = {"bot_name": "Own|🤖"}; h._settings_at -= 31; h._refresh_settings()
ok(h.ignore_bot_commands is True, "zonder [ChannelHint]-sectie ook aan")
print("ALLES OK")
