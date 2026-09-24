#!/usr/bin/env python3
"""Source patch: document this add-on's own config keys in config.ini.example.

Upstream checks every key in config.ini against config.ini.example at start and warns "unknown key ... (not documented
in config.ini.example)" for the rest. The keys below are this add-on's own settings (cards and generate_config.py) in
sections upstream documents; they work, the warning is only noise at every start. Upstream counts commented
"#key = value" lines as documented, so they are added as comments right under their section header. Sections the
example does not have are never checked, so they need nothing here.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()
EXAMPLE = ROOT / "config.ini.example"

KEYS = {
    "Bot": [
        ("protect_starred", "true", "add-on: keep contacts starred on the dashboard as favourites on the radio"),
        ("keep_radio_favourites", "true", "add-on: never remove the radio's favourites during contact cleanup"),
    ],
    "Feed_Manager": [
        ("default_max_item_age_minutes", "30", "add-on: ignore feed items older than this on a feed's first check"),
    ],
    "Help_Command": [
        ("list_url", "", "add-on: bare 'help' answers with this link to the full command list"),
    ],
}

lines = EXAMPLE.read_text(encoding="utf-8").splitlines(keepends=True)
for section, keys in KEYS.items():
    header = f"[{section}]"
    positions = [i for i, line in enumerate(lines) if line.strip() == header]
    if len(positions) != 1:
        sys.exit(f"PATCH FAILED - section {header} found {len(positions)} time(s) in config.ini.example (expected 1)")
    block = []
    for key, value, why in keys:
        block.append(f"# {why}\n")
        block.append(f"#{key} = {value}\n")
    lines[positions[0] + 1:positions[0] + 1] = block
EXAMPLE.write_text("".join(lines), encoding="utf-8")
print("Patched config.ini.example")
