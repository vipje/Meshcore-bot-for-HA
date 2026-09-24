"""F1: reading f1_sensor, the Dutch texts, and the plan of what to post when, over a whole race weekend."""
import json
import os
import pathlib as _pl
import sys

_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")
FIXTURES = str(_TESTS / "fixtures")
sys.path.insert(0, ADDON + "/local_shared")
sys.path.insert(0, FIXTURES)
import f1_data as F
import f1_states as S

_CATALOG = json.load(open(ADDON + "/local_shared/local_translations/nl.json"))


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


TZ = F.get_tz("Europe/Amsterdam")
CFG = {"timezone": "Europe/Amsterdam", "daily_time": "12:00", "post_daily": True, "reminder_minutes": 60, "post_results": True,
       "post_live": True, "live_milestones": [25, 50, 75], "max_live_posts": 8}

# ------------------------------------------------------------------ reading
snap = F.parse(S.states(S.ts(2026, 9, 21, 10)))
n = snap["next"]
check(n and n["round"] == "16" and n["season"] == "2026" and set(n["sessions"]) == {"fp1", "fp2", "fp3", "quali", "race"}, "volgende race met alle sessietijden")
check(n["race_ts"] == S.RACE_START, "racestart klopt (UTC)")
check(snap["last_race"]["round"] == "15" and len(snap["last_race"]["results"]) == 10 and snap["last_race"]["season"] == "2026", "laatste uitslag van de vorige race")
check(snap["standings_round"] == "15" and len(snap["drivers"]) == 10 and snap["drivers"][0]["code"] == "VER" and len(snap["teams"]) == 4, "klassementen")
check(snap["live"]["session"] == "unavailable" or snap["live"]["session"] is None, "live-sensoren 'unavailable' geven geen sessie")
check(snap["live"]["positions"] == [] and snap["live"]["lap"] is None, "en geen posities of ronde")
empty = F.parse([])
check(empty["next"] is None and empty["last_race"] is None and empty["drivers"] == [], "lege invoer geeft niets en geen fout")
renamed = [dict(s, entity_id=s["entity_id"].replace("sensor.f1_", "sensor.mijn_f1_")) for s in S.states(S.ts(2026, 9, 21, 10))]
check(F.parse(renamed)["next"] is not None, "een hernoemde entiteit (…f1_next_race) wordt ook gevonden")

# ------------------------------------------------------------------ texts
check(F.gp_name(n, TR) == "GP Italië (Monza)", "grand-prix-naam in het Nederlands")
now = S.ts(2026, 9, 21, 10)
cd = F.countdown_text(n, now, TZ, TR)
print("   ", cd)
check(cd.startswith("F1: nog 13 dagen tot de GP Italië (Monza), zo 4 okt 15:00") and len(cd.encode()) <= 130, "aftelbericht (zondag 15:00 lokale tijd)")
wk = F.week_texts(n, TZ, TR)
print("   ", wk)
check(wk[0].startswith("Raceweek: GP Italië (Monza)! vr VT1 13:30, VT2 17:00") and "za VT3 12:30, kwalificatie 16:00" in " | ".join(wk) and "zo race 15:00" in " | ".join(wk), "raceweek met de tijden per dag")
check(all(len(m.encode()) <= 130 for m in wk) and len(wk) <= 3, "raceweek past in maximaal 3 berichten van 130 bytes")
check(F.next_race_text(n, now, TZ, TR) == ["Volgende: GP Italië (Monza), zo 4 okt 15:00 (over 13 d)"], "commando f1: ver weg = één regel")
near = F.next_race_text(n, S.ts(2026, 10, 2, 8), TZ, TR)
check(len(near) >= 2 and near[0].startswith("Volgende:") and near[1].startswith("Raceweek:"), "commando f1: in de raceweek ook alle tijden")
check(F.reminder_text(n, "quali", S.ts(2026, 10, 3, 13, 0), TZ, TR) == "F1: over 60 min de kwalificatie van de GP Italië (Monza) (start 16:00)", "herinnering")
res = F.results_text("Uitslag", snap["last_race"]["results"])
check(res == ["Uitslag: 1 VER, 2 NOR, 3 PIA, 4 LEC, 5 HAM, 6 RUS, 7 SAI, 8 ALO, 9 GAS, 10 TSU"], "top 10 in één bericht")
check(F.winner_text(dict(snap["last_race"]), TR).startswith("Winnaar GP Singapore: Ver VERson (Red Bull), 1:34:12.500"), "winnaar met team en tijd")
st_txt = F.standings_texts(snap, "GP Italië (Monza)", TR)
check(st_txt[0].startswith("WK na GP Italië (Monza): 1 VER 288 | 2 NOR 276") and st_txt[1].startswith("Constructeurs: 1 McLaren 460"), "klassementen: rijders top 5 en constructeurs top 3")
check(F.fit("é" * 100).endswith("…") and len(F.fit("é" * 100).encode()) <= 130, "afkappen telt bytes, niet tekens")
check(F.gp_name({"country": "Hungary", "locality": "Budapest"}, TR) == "GP Hongarije (Budapest)" and F.gp_name({"country": "Monaco", "locality": "Monaco"}, TR) == "GP Monaco", "landen en gelijke plaatsnaam")

# ------------------------------------------------------------------ the plan over a whole weekend
T = 1800   # one tick = 30 minutes


def simulate(t0, t1, fn, cfg=CFG, st=None, step=T, keep_kinds=None):
    st = st if st is not None else {"posted": []}
    log = []
    t = t0
    while t <= t1:
        actions, upd = F.plan(F.parse(fn(t)), st, t, cfg, TR)
        st.update(upd)
        for a in actions:
            st["posted"].append(a["key"])
            if a["kind"] == "live":
                st["last_live_ts"] = t
            log.append((t, a))
        t += step
    return log, st


def weekend(t):
    if t < S.ts(2026, 10, 4, 14, 45):
        return S.states(t)
    return S.states(t, race_done=True, next_is_this=t < S.ts(2026, 10, 4, 20), standings_updated=t >= S.ts(2026, 10, 4, 15, 15))


log, st = simulate(S.ts(2026, 9, 20, 0), S.ts(2026, 10, 6, 0), weekend)
kinds = [a["kind"] for _, a in log]
print("   ", {k: kinds.count(k) for k in sorted(set(kinds))})
check(kinds.count("daily") == 12 and kinds.count("announce") == 1 and kinds.count("reminder") == 2 and kinds.count("result") == 1 and kinds.count("standings") == 1,
      "16 dagen: 12 aftelberichten, 1 aankondiging, 2 herinneringen, 1 uitslag, 1 klassement")
check(len(log) == 17 and len({a["key"] for _, a in log}) == 17, "17 berichten, geen enkele twee keer")
dailies = sorted(a["key"] for _, a in log if a["kind"] == "daily")
check(dailies[0] == "daily:2026-09-20" and dailies[-2] == "daily:2026-09-30" and dailies[-1] == "daily:2026-10-05" and "daily:2026-10-04" not in dailies, "aftellen van 20-09 t/m 30-09, niet op de racedag, weer vanaf 05-10")
ann = next(t for t, a in log if a["kind"] == "announce")
check(ann == S.ts(2026, 10, 1, 10), "aankondiging op 1 oktober 12:00 lokale tijd (10:00 UTC), 3 dagen voor de race")
check(all(F.to_local(t, TZ).hour >= 12 for t, a in log if a["kind"] in ("daily", "announce")), "nooit een dagelijks bericht vóór 12:00")
rem = {a["key"]: t for t, a in log if a["kind"] == "reminder"}
check(rem == {"remind:2026-16:quali": S.ts(2026, 10, 3, 13), "remind:2026-16:race": S.ts(2026, 10, 4, 12)}, "herinnering precies een uur voor kwalificatie en race")
res_t = next(t for t, a in log if a["kind"] == "result")
sta_t = next(t for t, a in log if a["kind"] == "standings")
check(res_t == S.ts(2026, 10, 4, 15, 0) and sta_t == S.ts(2026, 10, 4, 15, 30), "uitslag bij de eerste ronde nadat hij er is (14:45), klassement pas als het bij die ronde hoort (15:15)")
r_action = next(a for _, a in log if a["kind"] == "result")
check(r_action["round"] == "16" and r_action["season"] == "2026" and r_action["messages"][0].startswith("Uitslag GP Italië (Monza): 1 NOR, 2 VER") and r_action["messages"][-1].startswith("Winnaar"), "uitslagbericht voor ronde 16 met winnaar")

# a restart in the middle must not repeat anything
mid = S.ts(2026, 9, 27, 0)
part1, st1 = simulate(S.ts(2026, 9, 20, 0), mid, weekend)
st1 = json.loads(json.dumps(st1))                           # what the service stores and reads back
part2, _ = simulate(mid + T, S.ts(2026, 10, 6, 0), weekend, st=st1)
check(len(part1) + len(part2) == 17 and not ({a["key"] for _, a in part1} & {a["key"] for _, a in part2}), "herstart halverwege: niets dubbel, niets gemist")
# switched on in the middle of the day
mid_day, _ = simulate(S.ts(2026, 9, 25, 13), S.ts(2026, 9, 25, 23), weekend)
check([a["key"] for _, a in mid_day] == ["daily:2026-09-25"], "aangezet om 15:00: meteen het bericht van vandaag, één keer")
# settings
off, _ = simulate(S.ts(2026, 9, 20, 0), S.ts(2026, 10, 6, 0), weekend, cfg={**CFG, "post_daily": False, "reminder_minutes": 0, "post_results": False})
check(off == [], "alles uitgezet: geen enkel bericht")
noremind, _ = simulate(S.ts(2026, 9, 20, 0), S.ts(2026, 10, 6, 0), weekend, cfg={**CFG, "reminder_minutes": 0})
check(not [a for _, a in noremind if a["kind"] == "reminder"], "herinneringen uit")
old_result, _ = simulate(S.ts(2026, 10, 7, 0), S.ts(2026, 10, 7, 6), lambda t: S.states(t, race_done=True, next_is_this=False))
check(not [a for _, a in old_result if a["kind"] in ("result", "standings")], "een uitslag van meer dan 36 uur geleden wordt niet meer gepost")
nodata, _ = simulate(S.ts(2026, 9, 20, 0), S.ts(2026, 9, 21, 0), lambda t: [])
check(nodata == [], "zonder gegevens uit Home Assistant: niets en geen fout")

# ------------------------------------------------------------------ live: the race
def race_states(t, total=53, sc=(20, 22), red=None):
    lap = max(0, int((t - S.RACE_START) / 96)) if t >= S.RACE_START else 0
    lap = min(lap, total)
    status = "pre" if t < S.RACE_START else ("live" if lap < total else "finished")
    track = "CLEAR"
    if sc and sc[0] <= lap <= sc[1]:
        track = "SC"
    if red and red[0] <= lap <= red[1]:
        track, status = "RED", "suspended"
    return S.states(t, live_states=S.live("Race", status, lap, total, track))


lives, st = simulate(S.ts(2026, 10, 4, 12, 30), S.ts(2026, 10, 4, 14, 40), race_states, step=60)
lv = [(t, a) for t, a in lives if a["kind"] == "live"]
print("   ", [(a["key"].split(":")[0] + ":" + a["key"].split(":")[-1], a["messages"][0][:44]) for _, a in lv])
check(len(lv) == 5, f"race: start, 25%, 50%, 75% en safety car = 5 live-berichten (nu {len(lv)})")
check(lv[0][1]["key"] == "livestart:2026-16" and lv[0][1]["messages"][0] == "De race is gestart! GP Italië (Monza), 53 ronden", "startbericht")
pct = [a for _, a in lv if a["key"].startswith("livepct")]
check([a["key"].split(":")[-1] for a in pct] == ["25", "50", "75"] and pct[0]["messages"][0].startswith("Ronde 14/53: 1 VER | 2 NOR +3,400 | 3 LEC +5,100 | 4 PIA | 5 HAM"), "tussenstanden bij 25, 50 en 75% met kloof voor P2 en P3")
check(any(a["messages"][0].startswith("Safety car! (ronde 20/53)") for _, a in lv), "safety car één keer, met de ronde")
check(all(len(m.encode()) <= 130 for _, a in lv for m in a["messages"]), "alle live-berichten binnen 130 bytes")
gaps = [b[0] - a[0] for a, b in zip(lv, lv[1:])]
check(all(t >= 60 for t in gaps), "berichten komen niet in één keer achter elkaar")
lv_cap, _ = simulate(S.ts(2026, 10, 4, 12, 30), S.ts(2026, 10, 4, 14, 40), race_states, cfg={**CFG, "max_live_posts": 3}, step=60)
check(len([a for _, a in lv_cap if a["kind"] == "live"]) == 3, "maximum aantal live-berichten per race wordt gerespecteerd")
lv_off, _ = simulate(S.ts(2026, 10, 4, 12, 30), S.ts(2026, 10, 4, 14, 40), race_states, cfg={**CFG, "post_live": False}, step=60)
check(not [a for _, a in lv_off if a["kind"] == "live"], "live uit: geen live-berichten")
lv_un, _ = simulate(S.ts(2026, 10, 4, 12, 30), S.ts(2026, 10, 4, 14, 40), lambda t: S.states(t), step=60)
check(not [a for _, a in lv_un if a["kind"] == "live"], "live-sensoren niet beschikbaar: geen live-berichten en geen fout")
lv_red, _ = simulate(S.ts(2026, 10, 4, 12, 30), S.ts(2026, 10, 4, 14, 40), lambda t: race_states(t, sc=None, red=(30, 33)), step=60)
check(any(a["messages"][0].startswith("Rode vlag!") for _, a in lv_red if a["kind"] == "live"), "rode vlag wordt gemeld")
lv_m, _ = simulate(S.ts(2026, 10, 4, 12, 30), S.ts(2026, 10, 4, 14, 40), race_states, cfg={**CFG, "live_milestones": [50]}, step=60)
check([a["key"].split(":")[-1] for _, a in lv_m if a["key"].startswith("livepct")] == ["50"], "eigen mijlpalen (alleen 50%)")
# a plan that runs late (bot restarted mid-race) must not post a stale milestone
late, _ = simulate(S.ts(2026, 10, 4, 13, 58), S.ts(2026, 10, 4, 13, 58), race_states, st={"posted": []}, step=60)
check(not [a for _, a in late if a["key"].startswith("livepct")], "midden in de race opgestart (ronde 48): geen verlopen mijlpaal meer")

# ------------------------------------------------------------------ live: qualifying
def quali_states(t):
    status = "live" if t < S.ts(2026, 10, 3, 15, 0) else "finished"
    order = list(reversed(S.CODES[:20])) if t >= S.ts(2026, 10, 3, 14, 30) else S.CODES
    return S.states(t, live_states=S.live("Qualifying", status, None, order=order))


ql, _ = simulate(S.ts(2026, 10, 3, 13, 55), S.ts(2026, 10, 3, 15, 30), quali_states, step=60)
fin = [a for _, a in ql if a["kind"] == "live_final"]
print("   ", fin[0]["messages"] if fin else None)
check(len(fin) == 1 and fin[0]["messages"][0].startswith("Kwalificatie GP Italië (Monza): 1 COL, 2 BOR, 3 HAD"), "kwalificatie: uitslag uit de laatst geziene posities, één keer")
def short_quali(t):
    return S.states(t, live_states=S.live("Qualifying", "live" if t < S.ts(2026, 10, 3, 15) else "finished", None, order=S.CODES[:6]))
qs, _ = simulate(S.ts(2026, 10, 3, 13, 55), S.ts(2026, 10, 3, 15, 30), short_quali, step=60)
check(not [a for _, a in qs if a["kind"] == "live_final"], "minder dan 10 posities: geen kwalificatiebericht (liever niets dan onzin)")
prac, _ = simulate(S.ts(2026, 10, 2, 11, 25), S.ts(2026, 10, 2, 13, 0), lambda t: S.states(t, live_states=S.live("Practice 1", "live", None)), step=60)
check(not [a for _, a in prac if a["kind"] in ("live", "live_final")], "vrije training: geen live-berichten")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
