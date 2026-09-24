"""Home Assistant states shaped like the f1_sensor integration's (custom_components/f1_sensor/sensor.py).

The Italian GP of 2026-10-04 (Sunday, 13:00 UTC = 15:00 in the Netherlands), and the round before it. `states()` builds
what Home Assistant would hold at one moment: pass the live session, its status and the lap to get the live sensors.
"""
import datetime as _dt

UTC = _dt.timezone.utc


def iso(y, m, d, h, mi=0):
    return _dt.datetime(y, m, d, h, mi, tzinfo=UTC).isoformat()


def ts(y, m, d, h, mi=0):
    return _dt.datetime(y, m, d, h, mi, tzinfo=UTC).timestamp()


CODES = ["VER", "NOR", "LEC", "PIA", "HAM", "RUS", "SAI", "ALO", "GAS", "TSU", "ALB", "HUL", "STR", "OCO", "BEA", "LAW", "ANT", "HAD", "BOR", "COL"]
TEAMS = ["Red Bull", "McLaren", "Ferrari", "McLaren", "Ferrari", "Mercedes", "Williams", "Aston Martin", "Alpine", "Racing Bulls",
         "Williams", "Sauber", "Aston Martin", "Haas", "Haas", "Racing Bulls", "Mercedes", "Red Bull", "Sauber", "Alpine"]
SESSION_TIMES = {
    "first_practice": iso(2026, 10, 2, 11, 30), "second_practice": iso(2026, 10, 2, 15, 0), "third_practice": iso(2026, 10, 3, 10, 30),
    "qualifying": iso(2026, 10, 3, 14, 0), "race": iso(2026, 10, 4, 13, 0),
}
RACE_START = ts(2026, 10, 4, 13, 0)


def _sensor(key, state, attrs=None, domain="sensor"):
    return {"entity_id": f"{domain}.f1_{key}", "state": str(state), "attributes": attrs or {}}


def next_race(rnd="16", name="Italian Grand Prix", locality="Monza", country="Italy", sessions=None):
    a = {"season": "2026", "round": rnd, "race_name": name, "circuit_name": f"Circuit {locality}", "circuit_locality": locality,
         "circuit_country": country}
    for prefix, when in (sessions or SESSION_TIMES).items():
        a[f"{prefix}_start_utc"] = when
    return _sensor("next_race", (sessions or SESSION_TIMES)["race"], a)


def results(order, start_iso, rnd, name="Singapore Grand Prix", locality="Singapore", country="Singapore", key="last_race_results"):
    rows = []
    for i, code in enumerate(order, 1):
        idx = CODES.index(code) if code in CODES else 0
        rows.append({"position": str(i), "grid": str(i), "time": "1:34:12.500" if i == 1 else f"+{i * 3}.1s", "points": str(max(0, 26 - 2 * i)),
                     "status": "Finished", "driver": {"code": code, "givenName": code.title(), "familyName": code + "son"},
                     "constructor": {"name": TEAMS[idx]}})
    return _sensor(key, order[0], {"round": rnd, "race_name": name, "circuit_locality": locality, "circuit_country": country,
                                   "race_start_utc": start_iso, "results": rows})


def standings(rnd, order=None):
    order = order or CODES[:10]
    drivers = [{"position": str(i), "points": str(300 - 12 * i), "wins": str(max(0, 5 - i)),
                "Driver": {"code": c, "givenName": c.title(), "familyName": c + "son"}, "Constructors": [{"name": TEAMS[CODES.index(c)]}]}
               for i, c in enumerate(order, 1)]
    teams = [{"position": str(i), "points": str(500 - 40 * i), "wins": "1", "Constructor": {"name": n}}
             for i, n in enumerate(["McLaren", "Ferrari", "Red Bull", "Mercedes"], 1)]
    return [_sensor("driver_standings", len(drivers), {"season": "2026", "round": rnd, "driver_standings": drivers}),
            _sensor("constructor_standings", len(teams), {"season": "2026", "round": rnd, "constructor_standings": teams})]


def live(session, status, lap=None, total=53, track="CLEAR", order=None, gaps=True):
    order = order or CODES
    drivers = {str(i): {"tla": c, "name": c.title(), "team": TEAMS[CODES.index(c)], "current_position": str(i),
                        "gap_to_leader": (f"+{i * 1.7:.3f}" if i > 1 else "") if gaps else "", "retired": False} for i, c in enumerate(order, 1)}
    out = [_sensor("current_session", session), _sensor("session_status", status), _sensor("track_status", track),
           _sensor("driver_positions", lap if lap is not None else 0, {"drivers": drivers})]
    if lap is not None:
        out.append(_sensor("race_lap_count", lap, {"total_laps": total}))
    return out


def unavailable_live():
    return [_sensor(k, "unavailable") for k in ("current_session", "session_status", "track_status", "driver_positions", "race_lap_count")]


def states(now, *, race_done=False, next_is_this=True, live_states=None, standings_updated=True, sprint=False):
    """What Home Assistant holds at `now`. Before the race: results and standings of round 15. From 14:45 UTC on the
    race day: round 16's result, and its standings from 15:15."""
    out = []
    prev_start = iso(2026, 9, 13, 12, 0)
    if race_done:
        out.append(results(["NOR", "VER", "LEC", "PIA", "HAM", "RUS", "SAI", "ALO", "GAS", "TSU"], iso(2026, 10, 4, 13, 0), "16",
                           name="Italian Grand Prix", locality="Monza", country="Italy"))
        out += standings("16" if standings_updated else "15", ["NOR", "VER", "LEC", "PIA", "HAM", "RUS", "SAI", "ALO", "GAS", "TSU"])
    else:
        out.append(results(["VER", "NOR", "PIA", "LEC", "HAM", "RUS", "SAI", "ALO", "GAS", "TSU"], prev_start, "15"))
        out += standings("15")
    if next_is_this:
        out.append(next_race())
    else:
        out.append(next_race("17", "United States Grand Prix", "Austin", "USA", {"race": iso(2026, 10, 18, 19, 0), "qualifying": iso(2026, 10, 17, 22, 0)}))
    out += live_states if live_states is not None else unavailable_live()
    return out
