import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import configparser, sys, types
sys.path.insert(0, ADDON + "/local_shared")
from channel_hint import ChannelHint

OWN = "Mesh|HA|🤖"


def make(extra=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": OWN}
    cfg["ChannelHint"] = {"enabled": "true", "channels": "Publiek", "where": "#bot,#test", **(extra or {})}
    return ChannelHint(types.SimpleNamespace(config=cfg))


def is_bot(h, name):
    return h.is_other_bot(types.SimpleNamespace(sender_id=name))

# namen zoals ze op de mesh voorkomen (verzonnen voorbeelden in dezelfde vormen)
BOTS = ["D-XY-BOT-01", "DX1ABC-BOT", "ON0ABC-BOT", "BE-ExampleNode-BOT", "BE-XYZ-Town-Bot", "MeshCoreBot", "Echobot",
        # overige schrijfwijzen
        "Team Bot", "bot_nl", "NL-Bot 2", "BotAmsterdam", "Mesh|🤖", "weer-bot", "BOT", "Bot", "Test bot!", "AB|Bot|Limburg", "Robot Fan"]
PEOPLE = ["Alex", "Sam🖖", "Sam", "Klapperdeklap", "V", "LOWTECHNODE", "ABC01", "NW-AB-XY01", "WB Mobile 0A1B2C3D4E5F",
          "NL-AB-RP02 🗼", "MS-Westdorf", "DarkLordFalcon1", "1A2B3C4D", "cat_green", "DE-XX-K Musterdorf", "DXX000-AB12CD",
          "Botond", "BOTOND", "Bothe", "Abbott", "Robotnik", "Bottrop", "Bots-R-Us"[:0] or "Sebastiaan", "Both"]

h = make()
bad = [n for n in BOTS if not is_bot(h, n)] + [n for n in PEOPLE if is_bot(h, n)]
for n in BOTS: print(f"bot    {is_bot(h, n)!s:5} {n}")
for n in PEOPLE: print(f"mens   {is_bot(h, n)!s:5} {n}")
assert not bad, f"fout herkend: {bad}"

# eigen naam telt nooit als andere bot, ook al staat er 🤖 in
assert not is_bot(h, OWN) and not is_bot(h, OWN.upper())
# uitzetten: alleen de markers gelden
h2 = make({"bot_words": ""})
assert is_bot(h2, "Mesh|🤖") and not is_bot(h2, "DX1ABC-BOT")
# eigen woorden erbij
h3 = make({"bot_words": "robot,ai"})
assert is_bot(h3, "Robot Fan") and is_bot(h3, "Mesh-AI") and not is_bot(h3, "DX1ABC-BOT") and not is_bot(h3, "Robotnik") and not is_bot(h3, "Aidan")
# geen sender: geen bot
assert not is_bot(h, "") and not is_bot(h, None)
# note_message onthoudt een kanaal alleen voor bots, niet in DM's
m = types.SimpleNamespace(sender_id="DX1ABC-BOT", channel="Publiek", is_dm=False)
h.note_message(m); assert "publiek" in h._bot_seen
h._bot_seen.clear(); m.is_dm = True; h.note_message(m); assert not h._bot_seen
print("ALLES OK")
