#!/usr/bin/env python3
"""Source patch applied to the vendored meshcore-bot command manager.

Runs once during the Docker build, after the other command_manager patches
(see patch_webviewer.py for the shared rationale/mechanics).

Upstream only tells listeners (Discord/Telegram bridges, our Home Assistant
bridge) about *channel* messages the bot sends (bot.channel_sent_listeners).
Replies to a direct message - which includes everything the bot says in a
room server - are sent through _send_dm_payload() without any notification, so
they never showed up in the MeshCore Chat panel.

This adds the same kind of hook for DMs: after a successful send, every
callback in bot.dm_sent_listeners is scheduled with a synthetic event whose
payload is {'contact_public_key', 'contact_name', 'text'}. The list is created
lazily (getattr), so no change to core.py is needed; the Home Assistant bridge
service registers itself on it.
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
    """            # Handle result using unified handler
            return self._handle_send_result(
                result, "DM", contact_name, used_retry_method, rate_limit_key=rate_limit_key
            )
""",
    """            # Handle result using unified handler
            success = self._handle_send_result(
                result, "DM", contact_name, used_retry_method, rate_limit_key=rate_limit_key
            )
            # Tell DM-sent listeners (e.g. the Home Assistant bridge) about it.
            listeners = getattr(self.bot, "dm_sent_listeners", None)
            if success and listeners:
                if isinstance(contact, dict):
                    contact_key = contact.get("public_key", "") or ""
                else:
                    contact_key = getattr(contact, "public_key", "") or ""
                payload = {
                    "contact_public_key": contact_key,
                    "contact_name": contact_name,
                    "text": content,
                }
                synthetic_event = type("Event", (), {"payload": payload})()

                async def _run_dm_listener(listener, event):
                    try:
                        await listener(event, None)
                    except Exception as e:
                        self.logger.warning("DM sent listener error: %s", e, exc_info=True)

                for cb in list(listeners):
                    asyncio.create_task(_run_dm_listener(cb, synthetic_event))
            return success
""",
)
