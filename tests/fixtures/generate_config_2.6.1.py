#!/usr/bin/env python3
"""Turn the add-on options (/data/options.json) into the bot's config.ini.

Usage: generate_config.py <options.json> <config.ini> [data_dir]

Every option has a default here, so a missing or partially filled options file
(for example right after an upgrade) still produces a valid config instead of
crashing the bot.
"""
import configparser
import json
import os
import sqlite3
import sys

# Commands whose section name is not simply name.title() + "_Command"
# (see BaseCommand._derive_config_section_name in the bot).
CAMEL_CASE = {"dadjoke": "DadJoke", "webviewer": "WebViewer"}


# The bot name always ends with this, so people (and other bots) can see at a
# glance that a message comes from a bot. Not optional: it is appended
# automatically to whatever name is configured.
BOT_SUFFIX = "|\U0001F916"  # |🤖


def bot_name(name: str) -> str:
    # Strip any robot emoji / pipe the user typed at the end (with or without
    # the variation selector), so "Bot", "Bot 🤖" and "Bot|🤖" all become
    # "Bot|🤖" and never "Bot🤖|🤖".
    name = (name or "").strip().rstrip(" |\U0001F916\ufe0f")
    return (name or "MeshCoreBot") + BOT_SUFFIX


# Commands that stay off unless listed in commands.enable (they need internet
# services or are rarely wanted).
DEFAULT_OFF = ("airplanes", "worldcup")


def command_section(name: str) -> str:
    base = CAMEL_CASE.get(name.lower()) or name.strip().title()
    return f"{base}_Command"


def set_option(cfg: configparser.ConfigParser, section: str, key: str, value: str) -> None:
    if not cfg.has_section(section):
        cfg.add_section(section)
    cfg[section][key] = value


def bool_str(value) -> str:
    return "true" if value else "false"


def get(opts: dict, group: str, key: str, default):
    value = (opts.get(group) or {}).get(key)
    return default if value is None else value


def split_keyval(line: str, sep: str = "="):
    key, found, value = line.partition(sep)
    if not found or not key.strip():
        return None
    return key.strip(), value.strip()


def build(opts: dict, data_dir: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str  # keep key case as written
    g = lambda group, key, default="": get(opts, group, key, default)  # noqa: E731

    cfg["Connection"] = {
        "connection_type": g("connection", "type", "tcp"),
        "serial_port": g("connection", "serial_port"),
        "ble_device_name": g("connection", "ble_device_name"),
        "hostname": g("connection", "tcp_host", "localhost"),
        "tcp_port": str(g("connection", "tcp_port", 5010)),
        "timeout": "30",
        "reconnect_max_retries": "0",
        "reconnect_delay_seconds": "5",
    }

    cfg["Bot"] = {
        "bot_name": bot_name(g("bot", "name", "MeshCoreBot")),
        "enabled": "true",
        "db_path": f"{data_dir}/meshcore_bot.db",
        # Delay between the parts of a multi-message reply. Higher = more
        # breathing room on the mesh, at the cost of slower long replies.
        "bot_tx_rate_limit_seconds": str(g("bot", "tx_delay_seconds", 3.0)),
        # device = radio firmware adds contacts and overwrites the oldest
        # non-favourite; bot = the bot adds them; false = fully manual.
        "auto_manage_contacts": str(g("contacts", "mode", "device")),
        # See local_patches/patch_contact_protection.py.
        **({"timezone": str(g("bot", "timezone", "")).strip()} if str(g("bot", "timezone", "")).strip() else {}),
        "protect_starred": bool_str(g("contacts", "protect_starred", True)),
        "keep_radio_favourites": bool_str(g("contacts", "keep_radio_favourites", True)),
    }

    cfg["Channels"] = {
        "monitor_channels": ",".join(g("bot", "channels", ["test"])),
        "respond_to_dms": bool_str(g("bot", "respond_to_dms", True)),
    }

    cfg["Keywords"] = {}
    for line in g("advanced", "keywords", []):
        kv = split_keyval(line)
        if kv:
            cfg["Keywords"][kv[0]] = kv[1]

    # Only honoured for real DMs (which carry a verified public key); channel
    # messages have no cryptographic sender verification.
    cfg["Admin_ACL"] = {
        "admin_pubkeys": ",".join(k.lower() for k in g("bot", "admin_pubkeys", [])),
    }

    cfg["ContactCleanup"] = {
        "enabled": bool_str(g("contacts", "cleanup_enabled", False)),
        "trigger_at": str(g("contacts", "cleanup_at", 300)),
        "target": str(g("contacts", "cleanup_to", 250)),
        "keep_days": str(g("contacts", "cleanup_keep_days", 7)),
        "stale_enabled": bool_str(g("contacts", "stale_enabled", False)),
        "stale_repeater_days": str(g("contacts", "stale_repeater_days", 14)),
        "stale_other_days": str(g("contacts", "stale_other_days", 30)),
    }

    cfg["Notifications"] = {
        "enabled": bool_str(g("notifications", "enabled", False)),
        "destination": str(g("notifications", "destination", "room")),
        "target": str(g("notifications", "target", "")).strip(),
        "min_level": str(g("notifications", "min_level", "ERROR")),
        "events": ",".join(g("notifications", "events", [
            "startup", "radio", "room_login", "send_failed", "contacts_full",
            "ha_bridge", "command_error", "admin_command", "error"])),
        "cooldown_minutes": str(g("notifications", "cooldown_minutes", 30)),
        "digest_seconds": str(g("notifications", "digest_seconds", 60)),
        "daily_summary": bool_str(g("notifications", "daily_summary", True)),
        "summary_time": str(g("notifications", "summary_time", "08:00")),
        "ha_notify": bool_str(g("notifications", "ha_notify", True)),
        "ha_notify_service": str(g("notifications", "ha_notify_service", "")).strip(),
    }

    add_public_channel(cfg, opts)

    cfg["Feed_Manager"] = {
        "feed_manager_enabled": bool_str(g("commands", "feeds_enabled", True)),
        "default_max_item_age_minutes": str(g("commands", "feed_max_item_age_minutes", 30)),
    }

    precipitation = g("weather", "precipitation_unit", "mm")
    temperature = g("weather", "temperature_unit", "celsius")
    wind = g("weather", "wind_speed_unit", "kmh")
    cfg["Weather"] = {
        "default_country": g("weather", "default_country", "NL"),
        "weather_provider": g("weather", "provider", "openmeteo"),
        # gwx reads its units from [Weather], the plain wx command from [Wx_Command].
        "temperature_unit": temperature,
        "wind_speed_unit": wind,
        "precipitation_unit": precipitation,
    }
    cfg["Wx_Command"] = {"temperature_unit": temperature, "wind_speed_unit": wind}
    cfg["Rain_Command"] = {"amount_unit": precipitation}

    cfg["Webhook"] = {
        "enabled": bool_str(g("webhook", "enabled", True)),
        "host": "0.0.0.0",
        "port": str(g("webhook", "port", 8765)),
        "max_message_length": str(g("webhook", "max_message_length", 140)),
        "secret_token": g("webhook", "secret_token"),
    }

    cfg["RoomServer_Login"] = {
        "enabled": bool_str(g("room_server", "enabled", False)),
        "public_key": g("room_server", "public_key"),
        "password": g("room_server", "password"),
    }

    # lan_access false: listen only on the add-on's internal address (see patch_webviewer_ingress.py), so
    # the viewer port is closed to the local network and the dashboard is only reachable in the sidebar.
    # Without a known internal address the viewer stays open rather than locking you out.
    viewer_host = "0.0.0.0"
    if not g("webviewer", "lan_access", True):
        bind = os.environ.get("MESHCORE_VIEWER_BIND", "").strip()
        if bind:
            viewer_host = bind
        else:
            print("generate_config: webviewer.lan_access is off but the internal address is unknown; "
                  "leaving the viewer port open", file=sys.stderr)
    cfg["Web_Viewer"] = {
        "enabled": bool_str(g("webviewer", "enabled", True)),
        "host": viewer_host,
        "port": str(g("webviewer", "port", 8081)),
        "web_viewer_password": g("webviewer", "password"),
    }

    cfg["Logging"] = {
        "log_level": g("bot", "log_level", "INFO"),
        "log_file": f"{data_dir}/meshcore_bot.log",
        "colored_output": "false",
    }

    webhook_url = str(g("home_assistant", "webhook_url")).strip()
    cfg["HomeAssistantBridge"] = {
        "enabled": bool_str(bool(webhook_url)),
        "webhook_url": webhook_url,
        "node_prefix": str(g("home_assistant", "node_prefix")).strip(),
    }

    for name in DEFAULT_OFF:
        set_option(cfg, command_section(name), "enabled", "false")
    for name in g("commands", "enable", []):
        set_option(cfg, command_section(name), "enabled", "true")
    for name in g("commands", "disable", []):
        set_option(cfg, command_section(name), "enabled", "false")

    # Free-form overrides last, so they win over everything above.
    # Format: "Section.key = value"
    for line in g("advanced", "extra_config", []):
        target = split_keyval(line)
        if not target or "." not in target[0]:
            print(f"generate_config: ignoring extra_config line without 'Section.key': {line!r}",
                  file=sys.stderr)
            continue
        section, _, key = target[0].partition(".")
        set_option(cfg, section.strip(), key.strip(), target[1])

    return cfg


ANNOUNCE_PART_BYTES = 130
ANNOUNCE_MAX_PARTS = 3
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def compose_announcement(intro: str, items: list) -> list:
    """Pack the intro and the channel lines into at most 3 messages of <= 130 bytes.

    Colons are avoided because the scheduled-message format is `channel:message`.
    """
    def clean(text: str) -> str:
        text = " ".join(str(text).replace(":", " -").replace("\n", " ").split())
        return text if len(text.encode()) <= ANNOUNCE_PART_BYTES else text.encode()[:ANNOUNCE_PART_BYTES - 3].decode(
            "utf-8", "ignore") + "..."

    pieces = [clean(intro)] if str(intro).strip() else []
    for item in items:
        channel, _, description = str(item).partition("=")
        pieces.append(clean(f"{channel.strip()} {description.strip()}".strip()))
    parts: list = []
    current = ""
    for piece in pieces:
        if not piece:
            continue
        candidate = f"{current} | {piece}" if current else piece
        if len(candidate.encode()) <= ANNOUNCE_PART_BYTES:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = piece
    if current:
        parts.append(current)
    return parts[:ANNOUNCE_MAX_PARTS]


def add_public_channel(cfg: configparser.ConfigParser, opts: dict) -> None:
    """Greeter, command hints and a weekly announcement for a channel the bot listens on
    but runs no commands in (for example the public channel)."""
    g = lambda key, default="": get(opts, "public_channel", key, default)  # noqa: E731
    enabled = bool(g("enabled", False))
    channel = str(g("channel", "Public")).strip()
    where = list(g("command_channels", []))
    cfg["ChannelHint"] = {
        "enabled": bool_str(enabled and g("hint_enabled", True) and bool(channel)),
        "channels": channel,
        "where": ",".join(where),
        "message": str(g("hint_message", "We helpen je heel graag verder in {channels}")),
        "ignore_words": ",".join(g("hint_ignore_words", ["hello", "hi", "hey"])),
        "yield_seconds": str(g("yield_seconds", 15) if g("yield_to_other_bots", True) else 0),
        "cooldown_seconds": str(g("hint_cooldown_seconds", 120)),
    }
    if enabled and channel and g("greeter_enabled", True):
        cfg["Greeter_Command"] = {
            "enabled": "true",
            "channels": channel,
            "greeting_message": str(g("greeting", "Welkom @[{sender}]! Commando's? Probeer #bot of #test.")),
            "include_mesh_info": "false",
            "per_channel_greetings": "false",
            "rollout_days": str(g("greeter_rollout_days", 7)),
            # Wait a moment and skip the greeting if anyone (a person or another bot) already
            # greeted the newcomer by name in the meantime.
            "dead_air_delay_seconds": str(g("yield_seconds", 15) if g("yield_to_other_bots", True) else 0),
            "defer_to_human_greeting": bool_str(g("yield_to_other_bots", True)),
        }
    if enabled and channel and g("announcement_enabled", False):
        day = str(g("announcement_day", "sat")).lower()
        day = day if day in DAYS else "sat"
        try:
            hour, minute = [int(x) for x in str(g("announcement_time", "12:00")).split(":")]
        except ValueError:
            hour, minute = 12, 0
        parts = compose_announcement(g("announcement_intro", ""), list(g("announcement_channels", [])))
        cfg["Scheduled_Messages"] = {}
        for i, part in enumerate(parts):   # one minute apart so they go out in order
            total = hour * 60 + minute + i
            cron = f"{total % 60} {(total // 60) % 24} * * {day}"
            cfg["Scheduled_Messages"][cron] = f"{channel}:{part}"


def apply_maintenance(opts: dict, db_path: str) -> None:
    """Scheduled database backups are switched on through the bot's own
    bot_metadata table (the same place its Maintenance page writes to)."""
    values = {
        "maint.db_backup_enabled": bool_str(get(opts, "contacts", "backup_enabled", True)),
        "maint.db_backup_schedule": "daily",
        "maint.db_backup_time": str(get(opts, "contacts", "backup_time", "02:00")),
        "maint.db_backup_retention_count": str(get(opts, "contacts", "backup_keep", 7)),
        "maint.db_backup_dir": "/data/backups" if db_path.startswith("/data") else
                               db_path.rsplit("/", 1)[0] + "/backups",
    }
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS bot_metadata (
            key TEXT PRIMARY KEY, value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        for key, value in values.items():
            conn.execute(
                "INSERT OR REPLACE INTO bot_metadata (key, value, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)", (key, value))
        conn.commit()
    finally:
        conn.close()


STATE_FILE = "generated_keys.json"


def merge_with_existing(generated: configparser.ConfigParser, config_path: str, state_path: str):
    """Keep what was set in the bot's own dashboard, overwrite only what the add-on options manage.

    - Keys the options generate always win (the options are the source of truth for them).
    - Keys the options generated last time but no longer do are removed (option switched off or
      list entry deleted), so they fall back to the bot's defaults.
    - Everything else in the existing file (for example a command's Channels list set on the
      dashboard's Plugins page) is kept.
    Returns the merged parser and the list of keys generated this time.
    """
    merged = configparser.ConfigParser(interpolation=None, strict=False)
    merged.optionxform = str
    if os.path.exists(config_path):
        try:
            merged.read(config_path, encoding="utf-8")
        except (configparser.Error, OSError) as exc:
            print(f"generate_config: existing config unreadable, starting fresh: {exc}", file=sys.stderr)
            merged = configparser.ConfigParser(interpolation=None, strict=False)
            merged.optionxform = str

    now_keys = [[s, k] for s in generated.sections() for k in generated[s]]
    try:
        with open(state_path, encoding="utf-8") as fh:
            previous = json.load(fh)
    except (OSError, ValueError):
        previous = []
    still = {(s, k) for s, k in now_keys}
    for section, key in previous:
        if (section, key) not in still and merged.has_section(section):
            merged.remove_option(section, key)
    for section in generated.sections():
        if not merged.has_section(section):
            merged.add_section(section)
        for key, value in generated[section].items():
            merged[section][key] = value
    return merged, now_keys


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    options_path, config_path = sys.argv[1], sys.argv[2]
    data_dir = sys.argv[3] if len(sys.argv) > 3 else "/data"
    with open(options_path, encoding="utf-8") as fh:
        opts = json.load(fh)
    generated = build(opts, data_dir)
    state_path = os.path.join(data_dir, STATE_FILE)
    merged, keys = merge_with_existing(generated, config_path, state_path)
    with open(config_path, "w", encoding="utf-8") as fh:
        merged.write(fh)
    try:
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(keys, fh)
    except OSError as exc:
        print(f"generate_config: could not store generated key list: {exc}", file=sys.stderr)
    try:
        apply_maintenance(opts, f"{data_dir}/meshcore_bot.db")
    except Exception as exc:  # never stop the bot from starting over a backup setting
        print(f"generate_config: could not set backup schedule: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
