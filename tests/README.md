# Tests

Everything here runs **without building the add-on and without a radio**. The tests run against a copy of the
pinned upstream release (`--branch vX.Y.Z` in `meshcore-bot/Dockerfile`) that has the add-on's patches applied,
so they show two things at once: that our patches still fit upstream, and that our code behaves.

```
tests/run_all.sh
```

Needs `git` and `python3` (with `venv`); the first run also needs network to clone upstream and install the
Python packages into `$WORK` (default `/tmp/meshcore-tests`). `node` + `npm` are optional: with them the Bots
page is also run in a browser-like DOM (jsdom).

## What is covered

| Script | What it proves |
|---|---|
| `simulate_build.py` | Replays the Dockerfile's `COPY` and `python3 patch_*.py` steps on a clean upstream tree. A patch whose anchor text no longer occurs exactly once fails, like the real build. |
| `test_generator.py` | `generate_config.py` with real-shaped options: values of moved settings never change, dashboard changes survive a restart, a fresh install gets safe defaults, an existing announcement schedule is never removed. |
| `test_cards.py` | Every settings card on the Plugins page in the real web viewer: shows the right values, validates, saves without touching anything else, survives a restart. |
| `test_bots_page.py`, `ui_test.js` | The Bots page: API, CSRF, names shown as plain text only, and its behaviour in a DOM. |
| `test_ingress.py` | All dashboard pages with Home Assistant's ingress header (sidebar), with and without a password. |
| `test_channel_watchdog.py` | The channel check after a busy radio start (the failure of 2026-09-20). |
| `test_notify_limiter.py` | A notification must not use up the reply budget. |
| `test_botlist_greeter.py`, `test_bot_names.py`, `test_channel_hint_live.py` | Bot recognition, `botlist`, the greeter skipping bots, hint settings applied live. |
| `test_f1_data.py`, `test_f1_game.py`, `test_f1_service.py` | The F1 channel: reading `f1_sensor`, the Dutch texts, a plan over a whole race weekend (daily countdown, announcement, reminders, results, standings, live milestones, safety car, qualifying result) without repeats or stale posts; the prediction game keyed on the public key; the service posting, remembering across restarts, backing off when sending fails; the `f1` command. |
| `test_ha_parser.py`, `test_ha_service.py`, `test_rptr_info_notify.py` | The repeater data from Home Assistant, the service against a fake Home Assistant, `rptr`, `info bot`, the notices to the Notifications service.  |
| `test_ha_alerts.py` | The repeater warnings (restart, offline, noise floor, airtime, neighbour gone: each on, off, once per day, across a restart), battery history, trend text and `rptr accu`. |
| `test_heartbeat.py` | The heartbeat sensor against a fake Home Assistant: state, attributes, errors logged once, `stopped` on a clean stop, limits. |
| `test_community.py` | The community commands and games of 2.14.0 against the real classes: `topu` without bots (switch on and off, with the name list), the archive (keeps what upstream drops after 7 days), `dx`, `pad`, `sig`, `meshkaart`, `karma` (all its limits), `checkin` streaks, `prikbord`, `noodnummers`, `weetje`, `peiling`/`kies`, `herinner` and the Reminders service (on time, once, retry, give up, after a restart, language), `voorspel` (DM only, owner only, points), `buien` (Buienradar values, timeline), `xp`/`badge`, the Games page data (no bots, no public keys), hint text variants, `kenteken` with Belgian/German plates, `noodnummers`/`aed` answering by DM, every switch off, and no keyword clashes. |
| `test_housekeeping.py` | Room server re-login interval (card setting and limits), no "unknown key" warnings for the add-on's own keys while real typos are still reported, the contact-capacity cleanup that pauses 6 hours after a round that removed nothing, the room clock check / `clock sync`, and the Dockerfile staying small (layers, patch ORDER, .dockerignore). |
| `test_channel_radar.py` | The channel radar: recognising a hashtag channel by channel byte + MAC (a wrong MAC is not enough), the public channel, unknown channels, counting per day with one count per message, no double counting after a restart, names from the card, no message data in the summary. |
| `test_data_transfer.py` | Moving the bot: export to `/share/meshcore-bot/export/` only on request (database copied consistently, also what is still in the WAL), import only into a new installation (never over existing settings), options restored through a fake Supervisor (and what happens when it refuses), never blocking the start. |
| `test_translations.py` | nl and en translations have the same keys and every option has a text. |
| `test_local_translations.py` | Every `translate()` key used anywhere in `local_commands/`, `local_shared/` or `local_service_plugins/` (including dynamic ones like F1's country/session/day/month labels) exists in our own `local_shared/local_translations/{nl,en,de,fr}.json`. |
| `test_nl_completeness.py` | Every text in upstream's own `translations/en.json` has a Dutch translation, in upstream's own `nl.json` or in our local overlay (`keywords.*`, alternate trigger words rather than prose, are intentionally excluded). Catches upstream adding new English texts before the Dutch overlay is extended to match. |

`fixtures/` holds a sanitised copy of the add-on options (`options_sample.json`, no real secrets), the generator as
it was before settings moved to the dashboard (`generate_config_2.6.1.py`, to test the update path) and entity
states shaped like meshcore-ha's (`ha_states.py`).

## Upgrading upstream

1. Change the tag in `meshcore-bot/Dockerfile`.
2. Run `tests/run_all.sh`. Every `FAIL  patch_...` line is a patch that has to be adapted to the new upstream code.
3. Fix, run again, then check the tests that fail for reasons of behaviour.
