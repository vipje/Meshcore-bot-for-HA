"""F1 prediction game: keyed on the public key, locked at qualifying, scored once per race."""
import contextlib
import os
import pathlib as _pl
import sqlite3
import sys
import tempfile

_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")
sys.path.insert(0, ADDON + "/local_shared")
sys.path.insert(0, str(_TESTS / "fixtures"))
import json as _json
from f1_game import F1Game
import f1_data as F
import f1_states as S

_CATALOG = _json.load(open(ADDON + "/local_shared/local_translations/nl.json"))


def TR(key, **kwargs):
    node = _CATALOG
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return key
        node = node[part]
    return node.format(**kwargs) if isinstance(node, str) and kwargs else node


fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


class DB:
    def __init__(self, path):
        self.path = path

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        try:
            yield c
        finally:
            c.close()


g = F1Game(DB(tempfile.mkdtemp() + "/g.db"))
g.ensure_tables()
g.ensure_tables()          # twice is fine
CODES = {"VER", "NOR", "LEC", "PIA", "HAM"}
A, B, C, D = "aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32
NOW, LOCK = 1000.0, 5000.0

ok, msg = g.predict("2026", "16", A, "Alice", "nor", NOW, LOCK, CODES, TR)
check(ok and msg == "Genoteerd: je voorspelt NOR als winnaar." and g.pick_of("2026", "16", A) == "NOR", "voorspellen (hoofdletters maken niet uit)")
ok, msg = g.predict("2026", "16", A, "Alice", "VER", NOW, LOCK, CODES, TR)
check(ok and msg == "Aangepast: je voorspelt nu VER (was NOR)." and g.pick_of("2026", "16", A) == "VER" and g.players("2026", "16") == 1, "aanpassen vervangt de vorige keuze")
ok, msg = g.predict("2026", "16", A, "Alice", "VER", NOW, LOCK, CODES, TR)
check(ok and msg.startswith("Genoteerd") and g.players("2026", "16") == 1, "dezelfde keuze nogmaals: nog steeds één deelnemer")
ok, msg = g.predict("2026", "16", B, "Alice", "NOR", NOW, LOCK, CODES, TR)
check(ok and g.pick_of("2026", "16", A) == "VER" and g.pick_of("2026", "16", B) == "NOR" and g.players("2026", "16") == 2, "een andere sleutel met dezelfde naam raakt de keuze van Alice niet (niemand kan voor een ander stemmen)")
check(g.pick_of("2026", "16", A.upper()) == "VER", "sleutels zijn niet hoofdlettergevoelig")
ok, msg = g.predict("2026", "16", C, "Cor", "XXX", NOW, LOCK, CODES, TR)
check(not ok and "ken ik niet" in msg and g.players("2026", "16") == 2, "onbekende code wordt geweigerd")
ok, msg = g.predict("2026", "16", C, "Cor", "", NOW, LOCK, set(), TR)
check(not ok, "lege code wordt geweigerd")
ok, msg = g.predict("2026", "16", C, "Cor", "VERSTAPPEN", NOW, LOCK, set(), TR)
check(not ok and "3 letters" in msg, "meer dan 3 letters wordt geweigerd")
ok, msg = g.predict("2026", "16", "", "Zonder", "VER", NOW, LOCK, CODES, TR)
check(not ok and "sleutel" in msg and g.players("2026", "16") == 2, "zonder sleutel (kanaalbericht) wordt nooit geaccepteerd")
ok, msg = g.predict("2026", "16", C, "Cor", "VER", LOCK, LOCK, CODES, TR)
check(not ok and "gesloten" in msg and g.pick_of("2026", "16", C) is None, "vanaf de start van de kwalificatie gesloten")
ok, msg = g.predict("2026", "16", A, "Alice", "LEC", LOCK + 1, LOCK, CODES, TR)
check(not ok and g.pick_of("2026", "16", A) == "VER", "na de sluiting kan ook een bestaande keuze niet meer worden aangepast")
ok, msg = g.predict("2026", "16", C, "Cor", "PIA", NOW, None, CODES, TR)
check(ok, "zonder bekende sluitingstijd wordt wel geaccepteerd")
g.predict("2026", "16", D, "Dirk", "HAM", NOW, LOCK, CODES, TR)

# scoring
results = F._results(S.results(["NOR", "VER", "LEC", "PIA", "HAM"], "x", "16")["attributes"]["results"])
scored = g.score("2026", "16", results)
print("   ", scored)
check(scored == [("Alice", "NOR", 5), ("Alice", "VER", 2), ("Cor", "PIA", 0), ("Dirk", "HAM", 0)],
      "winnaar goed = 5, tweede of derde = 2, anders 0; beste eerst")
check(g.score("2026", "16", results) == [], "een race wordt maar één keer gescoord")
check(g.points_of("2026", A) == (2, 1) and g.points_of("2026", B) == (5, 1) and g.points_of("2026", "ee" * 32) == (0, 0), "punten per persoon")

# a second race and the standings
g.predict("2026", "17", A, "Alice (nieuwe naam)", "NOR", NOW + 100, LOCK, CODES, TR)
g.predict("2026", "17", B, "Bob", "LEC", NOW + 100, LOCK, CODES, TR)
g.score("2026", "17", F._results(S.results(["NOR", "LEC", "VER"], "x", "17")["attributes"]["results"]))
table = g.standings("2026", 5)
print("   ", table)
check(table[:2] == [("Alice (nieuwe naam)", 7, 2), ("Bob", 7, 2)], "stand: punten van beide races opgeteld, laatste naam getoond, gelijke stand op naam")
check(len(g.standings("2026", 1)) == 1 and g.standings("2025", 5) == [], "limiet en ander seizoen")
check(g.score("2026", "18", results) == [], "een race zonder deelnemers levert niets op")
print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
