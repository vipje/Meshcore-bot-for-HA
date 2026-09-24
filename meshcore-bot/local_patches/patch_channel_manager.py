#!/usr/bin/env python3
"""Source patch applied to the vendored meshcore-bot channel discovery.

Runs once during the Docker build, right after `git clone` (see
patch_webviewer.py for the shared rationale/mechanics).

fetch_all_channels() aborts its startup scan after 3 consecutive empty
channel slots, assuming channels are always packed contiguously from index
0. That assumption breaks for any real layout with an unused gap of 3+
slots between two configured channels (e.g. indices 5-7 empty between
#bot@4 and #test@8): the scan gives up before ever reaching the channel
past the gap, so it's silently missing from channel_manager's cache -
`feed subscribe` can't find it by name, and incoming messages on it fall
back to a generic "ChannelN" display name instead of the real one.
Bumping the threshold gives real-world gaps enough headroom without
scanning all the way to max_channels (40) on every restart.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")


patch(
    "modules/channel_manager.py",
    "        consecutive_empty = 0\n"
    "        max_consecutive_empty = 3  # Abort after 3 consecutive missing/empty channels",
    "        consecutive_empty = 0\n"
    "        max_consecutive_empty = 10  # Abort after 10 consecutive missing/empty channels"
    " (was 3 - too eager for real layouts with a gap before a higher-index channel)",
)
