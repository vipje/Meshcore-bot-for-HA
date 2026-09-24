#!/usr/bin/env python3
"""Source patch: show the webhook's secret token as a password field on its card.

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

Upstream declares `secret_token` on the Webhook card as a plain text field, so the token is sent to the
browser and shown in clear. As a `password` field the viewer never sends the value to the browser (the card
only says a value exists) and only saves a new token when you type one.
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
    "modules/service_plugins/webhook_service.py",
    '{"key": "secret_token", "label": "Secret token", "type": "str", "default": "",',
    '{"key": "secret_token", "label": "Secret token", "type": "password", "default": "",',
)
