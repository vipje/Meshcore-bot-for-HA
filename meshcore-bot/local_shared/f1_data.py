#!/usr/bin/env python3
"""Formula 1 for the #f1 channel: read Home Assistant's `f1_sensor`, write the texts, plan what to post when.

Pure functions, no I/O (see f1_service.py, f1_command.py). Input is the list `GET /api/states` returns.
Sensor shapes come from the integration's own code (custom_components/f1_sensor/sensor.py):

  sensor.f1_next_race            state = race start (UTC); attributes season, round, race_name, circuit_name,
                                 circuit_locality, circuit_country, <session>_start_utc for first_practice,
                                 second_practice, third_practice, sprint_qualifying, sprint, qualifying, race
  sensor.f1_last_race_results    attributes round, race_name, race_start_utc, results[{position, grid, time, points,
                                 status, driver{code, givenName, familyName}, constructor{name}}]
  sensor.f1_sprint_results       same shape for the sprint
  sensor.f1_driver_standings     attributes season, round, driver_standings[{position, points, wins, Driver, Constructors}]
  sensor.f1_constructor_standings attributes season, round, constructor_standings[{position, points, wins, Constructor}]
  live (only while a session runs): f1_current_session (Practice 1..3, Qualifying, Sprint Qualifying, Sprint, Race),
    f1_session_status (pre, live, suspended, break, finished, finalised, ended), f1_race_lap_count (state = lap,
    attribute total_laps), f1_driver_positions (attribute drivers{tla, name, current_position, gap_to_leader, ...}),
    f1_track_status (CLEAR, YELLOW, VSC, SC, RED)
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import pytz
except ImportError:  # pragma: no cover
    pytz = None

MAX_BYTES = 130
UNKNOWN = {"", "unknown", "unavailable", "none"}

# next-race attribute prefix -> short key (display label comes from translate("commands.f1.session.<short>"))
SESSIONS = [
    ("first_practice", "fp1"), ("second_practice", "fp2"), ("third_practice", "fp3"),
    ("sprint_qualifying", "sq"), ("sprint", "sprint"),
    ("qualifying", "quali"), ("race", "race"),
]
LIVE_RACE_SESSIONS = {"Race"}
LIVE_QUALI_SESSIONS = {"Qualifying", "Sprint Qualifying"}
FINISHED = {"finished", "finalised", "ended"}


# ------------------------------------------------------------------------------------------ helpers
def num(value: Any) -> Optional[float]:
    if value is None or str(value).strip().lower() in UNKNOWN:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def parse_time(value: Any) -> Optional[float]:
    if not value or str(value).strip().lower() in UNKNOWN:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def get_tz(name: str):
    if pytz is not None:
        try:
            return pytz.timezone(name or "Europe/Amsterdam")
        except Exception:  # noqa: BLE001 - unknown zone name
            return pytz.timezone("Europe/Amsterdam")
    return timezone.utc


def to_local(ts: float, tz) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc).astimezone(tz)


def fit(text: str, limit: int = MAX_BYTES) -> str:
    if len(text.encode("utf-8")) <= limit:
        return text
    while text and len((text + "…").encode("utf-8")) > limit:
        text = text[:-1]
    return text + "…"


def pack(head: str, pieces: list, sep: str = " | ", limit: int = MAX_BYTES, max_messages: int = 3) -> list:
    """Head + pieces as few messages of at most `limit` bytes as possible; the head starts the first message."""
    messages, current = [], head
    for piece in pieces:
        candidate = current + (sep if current.strip() and current != head else "") + piece
        if len(candidate.encode("utf-8")) <= limit:
            current = candidate
        else:
            if current.strip():
                messages.append(current)
            current = fit(piece, limit)
    if current.strip():
        messages.append(current)
    return [fit(m, limit) for m in messages[:max_messages]]


def code_of(driver: dict) -> str:
    code = (driver or {}).get("code") or (driver or {}).get("tla")
    if code:
        return str(code).upper()
    return str((driver or {}).get("familyName") or "???")[:3].upper()


# ------------------------------------------------------------------------------------------ reading
def _index(states: list) -> dict:
    return {s["entity_id"]: s for s in states or [] if isinstance(s, dict) and "entity_id" in s}


def _get(idx: dict, key: str, domain: str = "sensor") -> Optional[dict]:
    exact = idx.get(f"{domain}.f1_{key}")
    if exact is not None:
        return exact
    for eid, st in idx.items():           # a renamed entity still ends with f1_<key>
        if eid.startswith(domain + ".") and eid.endswith("f1_" + key):
            return st
    return None


def _attrs(state: Optional[dict]) -> dict:
    return (state or {}).get("attributes") or {}


def _results(raw: list) -> list:
    out = []
    for r in raw or []:
        d = r.get("driver") or r.get("Driver") or {}
        c = r.get("constructor") or r.get("Constructor") or {}
        out.append({
            "pos": str(r.get("position") or r.get("positionText") or ""),
            "grid": str(r.get("grid") or ""),
            "code": code_of(d),
            "given": d.get("givenName") or "",
            "family": d.get("familyName") or "",
            "team": c.get("name") or "",
            "time": r.get("time") or (r.get("Time") or {}).get("time") or "",
            "points": r.get("points") or "",
            "status": r.get("status") or "",
        })
    return [r for r in out if r["pos"]]


def parse(states: list) -> dict:
    """Everything the F1 service and command need, from one read of Home Assistant's states."""
    idx = _index(states)
    snap: dict = {"next": None, "last_race": None, "sprint": None, "drivers": [], "teams": [], "standings_round": None,
                  "standings_season": None, "live": {}}

    nxt = _get(idx, "next_race")
    if nxt is not None and str(nxt.get("state", "")).lower() not in UNKNOWN:
        a = _attrs(nxt)
        sessions = {}
        for prefix, short in SESSIONS:
            ts = parse_time(a.get(f"{prefix}_start_utc"))
            if ts is not None:
                sessions[short] = ts
        race_ts = sessions.get("race") or parse_time(nxt.get("state"))
        if race_ts is not None:
            sessions["race"] = race_ts
            snap["next"] = {
                "season": str(a.get("season") or ""), "round": str(a.get("round") or ""), "race_name": a.get("race_name") or "",
                "circuit": a.get("circuit_name") or "", "locality": a.get("circuit_locality") or "",
                "country": a.get("circuit_country") or "", "sessions": sessions, "race_ts": race_ts,
            }

    for key, target in (("last_race_results", "last_race"), ("sprint_results", "sprint")):
        st = _get(idx, key)
        a = _attrs(st)
        results = _results(a.get("results"))
        if results:
            start = parse_time(a.get("race_start_utc") or a.get("sprint_start_utc"))
            snap[target] = {
                "round": str(a.get("round") or ""), "race_name": a.get("race_name") or "", "country": a.get("circuit_country") or "",
                "locality": a.get("circuit_locality") or "", "start_ts": start, "results": results,
                "season": str(datetime.fromtimestamp(start, timezone.utc).year) if start else "",
            }

    ds = _attrs(_get(idx, "driver_standings"))
    for r in ds.get("driver_standings") or []:
        d = r.get("Driver") or {}
        teams = r.get("Constructors") or []
        snap["drivers"].append({"pos": str(r.get("position") or ""), "code": code_of(d), "family": d.get("familyName") or "",
                                "given": d.get("givenName") or "", "team": (teams[-1].get("name") if teams else "") or "",
                                "points": r.get("points") or "0", "wins": r.get("wins") or "0"})
    cs = _attrs(_get(idx, "constructor_standings"))
    for r in cs.get("constructor_standings") or []:
        snap["teams"].append({"pos": str(r.get("position") or ""), "name": (r.get("Constructor") or {}).get("name") or "",
                              "points": r.get("points") or "0", "wins": r.get("wins") or "0"})
    snap["standings_round"] = str(ds.get("round") or "") or None
    snap["standings_season"] = str(ds.get("season") or "") or None

    # live sensors (only meaningful while a session runs)
    def state_of(key):
        st = _get(idx, key)
        value = None if st is None else str(st.get("state", "")).strip()
        return None if value is None or value.lower() in UNKNOWN else value

    live = {"session": state_of("current_session"), "status": (state_of("session_status") or "").lower() or None,
            "track": (state_of("track_status") or "").upper() or None, "lap": None, "total_laps": None, "positions": []}
    lap = num(state_of("race_lap_count"))
    live["lap"] = int(lap) if lap is not None else None
    total = num(_attrs(_get(idx, "race_lap_count")).get("total_laps"))
    live["total_laps"] = int(total) if total else None
    drivers = _attrs(_get(idx, "driver_positions")).get("drivers") or {}
    rows = []
    for d in drivers.values() if isinstance(drivers, dict) else []:
        pos = num(d.get("current_position"))
        if pos is not None:
            rows.append({"pos": int(pos), "code": str(d.get("tla") or "").upper(), "name": d.get("name") or "",
                         "gap": d.get("gap_to_leader") or "", "retired": bool(d.get("retired"))})
    live["positions"] = sorted(rows, key=lambda r: r["pos"])
    snap["live"] = live
    return snap


# ------------------------------------------------------------------------------------------ texts
def gp_name(nxt: dict, translate) -> str:
    raw_country = nxt.get("country") or ""
    country = translate(f"commands.f1.country.{raw_country}") if raw_country else ""
    place = nxt.get("locality") or ""
    if country and place and place.lower() != country.lower():
        return f"GP {country} ({place})"
    return f"GP {country or place or nxt.get('race_name') or '?'}"


def gp_name_of(item: dict, translate) -> str:
    return gp_name(
        {"country": item.get("country"), "locality": item.get("locality"), "race_name": item.get("race_name")}, translate
    )


def fmt_day(dt: datetime, translate) -> str:
    return f"{translate(f'commands.f1.day.{dt.weekday()}')} {dt.day} {translate(f'commands.f1.month.{dt.month}')}"


def fmt_hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def countdown_text(nxt: dict, now_ts: float, tz, translate) -> str:
    race = to_local(nxt["race_ts"], tz)
    days = (race.date() - to_local(now_ts, tz).date()).days
    when = f"{fmt_day(race, translate)} {fmt_hm(race)}"
    if days <= 0:
        return fit(translate("commands.f1.today", gp=gp_name(nxt, translate), time=fmt_hm(race)))
    unit_key = "commands.f1.day_unit" if days == 1 else "commands.f1.days_unit"
    return fit(translate("commands.f1.countdown", days=days, unit=translate(unit_key), gp=gp_name(nxt, translate), when=when))


def week_texts(nxt: dict, tz, translate) -> list:
    """The race weekend as a few messages: one piece per day with its sessions."""
    by_day: dict = {}
    for short in ("fp1", "fp2", "fp3", "sq", "sprint", "quali", "race"):
        ts = nxt["sessions"].get(short)
        if ts is not None:
            local = to_local(ts, tz)
            by_day.setdefault(local.date(), []).append((short, local))
    pieces = []
    for day in sorted(by_day):
        items = by_day[day]
        first = items[0][1]
        pieces.append(
            f"{translate(f'commands.f1.day.{first.weekday()}')} "
            + ", ".join(f"{translate(f'commands.f1.session.{s}')} {fmt_hm(dt)}" for s, dt in items)
        )
    return pack(translate("commands.f1.raceweek", gp=gp_name(nxt, translate)), pieces)


def next_race_text(nxt: dict, now_ts: float, tz, translate) -> list:
    if not nxt:
        return [translate("commands.f1.no_next_race")]
    race = to_local(nxt["race_ts"], tz)
    days = (race.date() - to_local(now_ts, tz).date()).days
    head = translate("commands.f1.next_race", gp=gp_name(nxt, translate), day=fmt_day(race, translate), time=fmt_hm(race))
    if days > 0:
        head += translate("commands.f1.in_days", days=days)
    if days > 3:
        return [fit(head)]
    return [fit(head)] + week_texts(nxt, tz, translate)


def reminder_text(nxt: dict, short: str, now_ts: float, tz, translate) -> str:
    start = to_local(nxt["sessions"][short], tz)
    mins = max(1, int(round((nxt["sessions"][short] - now_ts) / 60 / 5.0)) * 5)
    return fit(translate(
        "commands.f1.reminder", mins=mins, session=translate(f"commands.f1.session.{short}"),
        gp=gp_name(nxt, translate), time=fmt_hm(start),
    ))


def results_text(title: str, results: list, limit: int = 10) -> list:
    pieces = [f"{r['pos']} {r['code']}" for r in results[:limit]]
    return pack(f"{title}: ", pieces, sep=", ")


def winner_text(item: dict, translate) -> str:
    r = item["results"][0]
    extra = f", {r['time']}" if r["time"] else ""
    return fit(translate(
        "commands.f1.winner", gp=gp_name_of(item, translate), given=r["given"], family=r["family"], team=r["team"], extra=extra
    ))


def standings_texts(snap: dict, after: str, translate, drivers: int = 5, teams: int = 3) -> list:
    out = []
    if snap["drivers"]:
        out += pack(
            translate("commands.f1.standings_header", after=after),
            [f"{d['pos']} {d['code']} {d['points']}" for d in snap["drivers"][:drivers]],
        )[:1]
    if snap["teams"]:
        out += pack(
            translate("commands.f1.constructors_header"),
            [f"{t['pos']} {t['name']} {t['points']}" for t in snap["teams"][:teams]],
        )[:1]
    return out


def live_text(live: dict, translate, top: int = 5) -> str:
    lap, total = live.get("lap"), live.get("total_laps")
    head = translate("commands.f1.lap_header", lap=lap, total=total) if lap and total else translate("commands.f1.standing_header")
    pieces = []
    for r in live["positions"][:top]:
        gap = r["gap"] if (r["pos"] in (2, 3) and r["gap"]) else ""
        pieces.append(f"{r['pos']} {r['code']}" + (f" {gap}".replace(".", translate('commands.f1.decimal_sep')) if gap else ""))
    return fit(head + " | ".join(pieces))


def now_text(snap: dict, translate) -> list:
    live = snap["live"]
    if live.get("session") and live.get("status") in ("live", "suspended", "break", "pre"):
        status = translate(f"commands.f1.status.{live['status']}")
        head = f"{live['session']} {status}"
        if live["positions"]:
            return [fit(f"{head} | {live_text(live, translate)}")]
        return [fit(head + (
            translate("commands.f1.lap_suffix", lap=live["lap"], total=live["total_laps"])
            if live.get("lap") and live.get("total_laps") else ""
        ))]
    return []


# ------------------------------------------------------------------------------------------ planning
def _hhmm(text: str) -> tuple:
    try:
        h, m = str(text).split(":")
        return int(h), int(m)
    except (ValueError, AttributeError):
        return 12, 0


def plan(snap: dict, st: dict, now_ts: float, cfg: dict, translate) -> tuple:
    """(actions, state_updates): what to post now, and what to remember for the next round.

    Each action = {key, kind, messages, ...}; the service marks `key` as posted after it was sent, so a restart never
    repeats a message. `st` = {posted: [...], track, last_positions, last_live_ts}. `cfg` keys: timezone, daily_time,
    post_daily, reminder_minutes, post_results, post_live, live_milestones, max_live_posts. `translate` fixes the
    service's own posting language (a card setting); it is not per-sender since these posts have no sender."""
    tz = get_tz(cfg.get("timezone"))
    posted = set(st.get("posted", []))
    actions: list = []
    upd: dict = {}
    local = to_local(now_ts, tz)
    nxt, last, live = snap.get("next"), snap.get("last_race"), snap.get("live") or {}

    def add(key: str, kind: str, messages: list, **extra) -> None:
        if key not in posted and messages:
            actions.append({"key": key, "kind": kind, "messages": messages, **extra})

    rk = f"{nxt['season']}-{nxt['round']}" if nxt else None

    # 1. daily countdown, then the announcement of the race weekend
    if nxt and cfg.get("post_daily", True) and nxt["race_ts"] > now_ts and (local.hour, local.minute) >= _hhmm(cfg.get("daily_time", "12:00")):
        days = (to_local(nxt["race_ts"], tz).date() - local.date()).days
        raced_today = bool(last and last.get("start_ts") and to_local(last["start_ts"], tz).date() == local.date())
        if days > 3:
            if not raced_today:               # not on the evening of a race, when the result is what people want
                add(f"daily:{local.date().isoformat()}", "daily", [countdown_text(nxt, now_ts, tz, translate)])
        else:
            add(f"announce:{rk}", "announce", week_texts(nxt, tz, translate))

    # 2. reminders shortly before qualifying, sprint and race
    minutes = int(cfg.get("reminder_minutes", 60) or 0)
    if nxt and minutes > 0:
        for short in ("sq", "quali", "sprint", "race"):
            ts = nxt["sessions"].get(short)
            if ts is not None and 0 < ts - now_ts <= minutes * 60:
                add(f"remind:{rk}:{short}", "reminder", [reminder_text(nxt, short, now_ts, tz, translate)])

    # 3. results (from Jolpica, so authoritative) and the standings after them
    if cfg.get("post_results", True):
        for item, kind, label_key in (
            (last, "result", "commands.f1.result_label"), (snap.get("sprint"), "sprint_result", "commands.f1.sprint_label")
        ):
            if not item or not item["results"] or not item.get("start_ts") or not (0 < now_ts - item["start_ts"] < 36 * 3600):
                continue
            key = f"{kind}:{item['season']}-{item['round']}"
            msgs = results_text(f"{translate(label_key)} {gp_name_of(item, translate)}", item["results"])
            if kind == "result":
                msgs.append(winner_text(item, translate))
            add(key, kind, msgs, season=item["season"], round=item["round"], results=item["results"])
            if kind == "result" and snap.get("standings_round") == item["round"] and snap.get("standings_season") in (item["season"], None):
                add(
                    f"standings:{item['season']}-{item['round']}", "standings",
                    standings_texts(snap, gp_name_of(item, translate), translate),
                )

    # 4. live: race milestones, safety car / red flag, and qualifying results from the last positions seen
    if cfg.get("post_live", True) and live.get("session") and nxt and abs(nxt["race_ts"] - now_ts) < 4 * 86400:
        sess, status, lap, total = live["session"], live.get("status"), live.get("lap"), live.get("total_laps")
        used = sum(1 for k in posted if k.startswith((f"livepct:{rk}", f"livestart:{rk}", f"trk:{rk}")))
        room = used < int(cfg.get("max_live_posts", 8))
        spaced = now_ts - float(st.get("last_live_ts", 0)) >= 180
        if status == "live" and live["positions"]:
            upd["last_positions"] = {"session": sess, "ts": now_ts, "positions": live["positions"][:12]}
        if sess in LIVE_RACE_SESSIONS and status == "live" and lap and total and room:
            if lap <= 3:
                add(
                    f"livestart:{rk}", "live",
                    [fit(translate("commands.f1.race_started", gp=gp_name(nxt, translate), laps=total))],
                )
            if spaced:
                for pct in cfg.get("live_milestones", [25, 50, 75]):
                    threshold = math.ceil(total * int(pct) / 100)
                    if threshold <= lap < total and lap - threshold <= 5 and live["positions"]:
                        add(f"livepct:{rk}:{pct}", "live", [live_text(live, translate)])
        track = live.get("track")
        if track != st.get("track"):
            upd["track"] = track
            if track in ("SC", "RED") and sess in ("Race", "Sprint") and status in ("live", "suspended") and room:
                where = translate("commands.f1.lap_where", lap=lap, total=total) if lap and total else ""
                text = (
                    translate("commands.f1.safety_car", where=where) if track == "SC"
                    else translate("commands.f1.red_flag", where=where)
                )
                add(f"trk:{rk}:{sess}:{track}:{int(now_ts // 60)}", "live", [fit(text)])
        cached = st.get("last_positions") or {}
        if sess in LIVE_QUALI_SESSIONS and status in FINISHED and cached.get("session") == sess and len(cached.get("positions", [])) >= 10:
            label = translate("commands.f1.quali_label") if sess == "Qualifying" else translate("commands.f1.sprint_quali_label")
            add(f"livefin:{rk}:{sess}", "live_final", results_text(f"{label} {gp_name(nxt, translate)}",
                [{"pos": str(r["pos"]), "code": r["code"]} for r in cached["positions"]]))

    return actions, upd
