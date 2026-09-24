#!/usr/bin/env python3
"""Source patch: split long replies at a " | " separator when possible.

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

A reply that is too long for one radio message is split by
CommandManager.split_text_into_utf8_chunks(), which cut on the last newline or else the last
space that fits. For replies made of " | "-separated parts, such as the `test` reply
("ack @[name] | path (14 hops) | SNR: 10.0 dB | RSSI: -91 dBm | Received at: 22:13:34"), that
often cut in the middle of a part and left the value alone in the second message ("Received at:"
in one message, "22:13:34" in the next).

Now the split prefers a " | " boundary, so every message consists of complete parts, and the
separator that ends up at the start of the next message is dropped. Text without " | " splits
exactly as before. It is a single central function, so this covers every command and both channel
messages and DMs.
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
    "modules/command_manager.py",
    """            window = remaining[:fit]
            # Prefer newline, then space, within the fitting window
            split_at = window.rfind("\\n")
            if split_at <= 0:
                split_at = window.rfind(" ")
            if split_at <= 0:
                split_at = fit
""",
    """            window = remaining[:fit]
            # Prefer newline, then a " | " separator, then space, within the fitting window
            split_at = window.rfind("\\n")
            if split_at <= 0:
                if remaining[fit:fit + 3] == " | ":
                    split_at = fit          # the window ends exactly before a separator
                else:
                    split_at = window.rfind(" | ")
            if split_at <= 0:
                split_at = window.rfind(" ")
            if split_at <= 0:
                split_at = fit
""",
)
patch(
    "modules/command_manager.py",
    """            chunks.append(chunk)
            remaining = remaining[split_at:].lstrip("\\n ")
        return chunks if chunks else [""]""",
    """            chunks.append(chunk)
            remaining = remaining[split_at:].lstrip("\\n ")
            if remaining.startswith("| "):
                remaining = remaining[2:]   # the separator we cut at does not start the next message
        return chunks if chunks else [""]""",
)
