#!/usr/bin/env bash
# Runs every test against a patched copy of the pinned upstream release, without building the add-on.
#
#   tests/run_all.sh            (WORK=/some/dir to choose where the clone, the venv and the copy live)
#
# Needs: git, python3 (with venv), network for the first run. node + npm are optional (browser-like page test).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ADDON="$HERE/../meshcore-bot"
WORK="${WORK:-/tmp/meshcore-tests}"
TAG="$(grep -o -- '--branch v[0-9][0-9.]*' "$ADDON/Dockerfile" | head -1 | awk '{print $2}')"
[ -n "$TAG" ] || { echo "cannot find the upstream tag in the Dockerfile"; exit 2; }
mkdir -p "$WORK"

if [ ! -d "$WORK/upstream-$TAG" ]; then
  echo "== cloning upstream $TAG"
  git clone -q --depth 1 --branch "$TAG" https://github.com/agessaman/meshcore-bot.git "$WORK/upstream-$TAG" || exit 2
fi
if [ ! -x "$WORK/venv/bin/python" ]; then
  echo "== creating the test environment"
  python3 -m venv "$WORK/venv" || exit 2
  "$WORK/venv/bin/pip" install -q flask flask-socketio "flask-compress==1.15" requests pytz python-dateutil aiosqlite \
      geopy maidenhead aiohttp apscheduler feedparser meshcore pyyaml || exit 2
fi
PY="$WORK/venv/bin/python"

echo "== applying the add-on's patches to upstream $TAG (the build fails here if upstream moved)"
rm -rf "$WORK/sim"; mkdir -p "$WORK/sim"; cp -r "$WORK/upstream-$TAG/." "$WORK/sim/"   # a real copy, never a link to the clean clone
"$PY" "$HERE/simulate_build.py" "$WORK/sim" "$ADDON" | tail -25
BUILD=${PIPESTATUS[0]}
export SIM_TREE="$WORK/sim"

fails=0; total=0
run() {   # run <label> <command...>
  local label="$1"; shift
  local out; out="$("$@" 2>&1)"; local code=$?
  total=$((total + 1))
  if [ $code -eq 0 ]; then printf "  ok    %s\n" "$label"; else printf "  FAIL  %s\n" "$label"; echo "$out" | grep -E "^FAIL|Traceback|Error|fouten" | head -8 | sed 's/^/          /'; fails=$((fails + 1)); fi
}
[ "$BUILD" -eq 0 ] || { echo "  FAIL  build simulation"; fails=$((fails + 1)); }

echo "== tests"
cd "$WORK/sim"
run "channel watchdog"                 "$PY" "$HERE/test_channel_watchdog.py"
run "notification rate-limit fix"      "$PY" "$HERE/test_notify_limiter.py"
run "botlist + greeter skips bots"     "$PY" "$HERE/test_botlist_greeter.py"
run "bot name recognition"             "$PY" "$HERE/test_bot_names.py"
run "channel hint settings live"       "$PY" "$HERE/test_channel_hint_live.py"
run "repeater parser (meshcore-ha)"    "$PY" "$HERE/test_ha_parser.py"
run "repeater service"                 "$PY" "$HERE/test_ha_service.py" "$SIM_TREE"
run "rptr, info bot, low-battery notice" "$PY" "$HERE/test_rptr_info_notify.py" "$SIM_TREE"
run "heartbeat service"                "$PY" "$HERE/test_heartbeat.py" "$SIM_TREE"
run "repeater alerts, accu history, rptr accu" "$PY" "$HERE/test_ha_alerts.py" "$SIM_TREE"
run "translations (nl/en, all options)"  "$PY" "$HERE/test_translations.py"
run "our own translations (nl/en/de/fr)" "$PY" "$HERE/test_local_translations.py"
run "Dutch, German, French coverage of upstream texts" "$PY" "$HERE/test_nl_completeness.py" "$SIM_TREE"
run "F1: data, texts and posting plan" "$PY" "$HERE/test_f1_data.py"
run "F1: prediction game"            "$PY" "$HERE/test_f1_game.py"
run "F1: service and f1 command"      "$PY" "$HERE/test_f1_service.py" "$SIM_TREE"
run "community commands, games, topu without bots" "$PY" "$HERE/test_community.py" "$SIM_TREE"
run "housekeeping: room login, config keys, contact capacity" "$PY" "$HERE/test_housekeeping.py" "$SIM_TREE"
run "channel radar (Kanaalradar)" "$PY" "$HERE/test_channel_radar.py" "$SIM_TREE"
run "export/import via /share (moving the bot)" "$PY" "$HERE/test_data_transfer.py"
run "generate_config (options -> config.ini)" "$PY" "$HERE/test_generator.py"
run "settings cards (Plugins page)"    "$PY" "$HERE/test_cards.py" "$SIM_TREE"
run "Bots page"                        "$PY" "$HERE/test_bots_page.py" "$SIM_TREE"
run "sidebar (ingress), no password"   "$PY" "$HERE/test_ingress.py" "$SIM_TREE" ""
run "sidebar (ingress), with password" "$PY" "$HERE/test_ingress.py" "$SIM_TREE" "secret"

if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  if [ ! -d "$WORK/jsd/node_modules/jsdom" ]; then
    mkdir -p "$WORK/jsd"; ( cd "$WORK/jsd" && npm init -y >/dev/null 2>&1 && npm install --silent --no-audit --no-fund jsdom >/dev/null 2>&1 )
  fi
  "$PY" "$HERE/gen_bots_html.py" "$SIM_TREE" "$WORK/bots.html" >/dev/null 2>&1
  run "Bots page in a browser-like DOM"  env NODE_PATH="$WORK/jsd/node_modules" node "$HERE/ui_test.js" "$WORK/bots.html"
else
  echo "  skip  Bots page in a browser-like DOM (node/npm not installed)"
fi

echo "== $((total - fails)) of $total passed"
exit $fails
