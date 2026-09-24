#!/usr/bin/env python3
"""Source patch applied to the vendored meshcore-bot webhook service.

Runs once during the Docker build, right after `patch_disabled_command_notice.py`
(see patch_webviewer.py for the shared rationale/mechanics).

Achtste patch: webhook_service.py truncates any message over
max_message_length instead of splitting it - a longer payload (e.g. a P2000
alert forwarded from Home Assistant) silently loses its tail. Splits into
multiple same-sized messages instead, sent in order to the same
channel/DM. max_message_length is now set to 140 in run.sh (the meshcore
phone app itself only composes/sends up to ~142 chars per message), so a
longer alert now arrives as 2-3 short messages instead of one cut-off one.
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
    """        # Truncate to configured limit
        if len(message_text) > self.max_message_length:
            message_text = message_text[: self.max_message_length]""",
    """        # Split into multiple messages rather than truncating - a longer
        # payload (e.g. a P2000 alert) arrives as several short messages
        # instead of silently losing its tail.
        message_chunks = [
            message_text[i:i + self.max_message_length]
            for i in range(0, len(message_text), self.max_message_length)
        ] or [message_text]""",
)

patch(
    "modules/service_plugins/webhook_service.py",
    """                sent = await self._send_channel_message(
                    channel, message_text, scope=mesh_scope
                )
                if not sent:
                    self.logger.error(
                        f"Webhook: failed to send to channel '{channel}' from {request.remote}"
                    )
                    return aio_web.Response(
                        status=500,
                        content_type="application/json",
                        text='{"error": "Failed to send message"}',
                    )
                self.logger.info(
                    f"Webhook: sent to #{channel} from {request.remote}: "
                    f"{message_text[:60]}{'...' if len(message_text) > 60 else ''}"
                )""",
    """                for chunk in message_chunks:
                    sent = await self._send_channel_message(
                        channel, chunk, scope=mesh_scope
                    )
                    if not sent:
                        self.logger.error(
                            f"Webhook: failed to send to channel '{channel}' from {request.remote}"
                        )
                        return aio_web.Response(
                            status=500,
                            content_type="application/json",
                            text='{"error": "Failed to send message"}',
                        )
                self.logger.info(
                    f"Webhook: sent to #{channel} from {request.remote} in "
                    f"{len(message_chunks)} part(s): "
                    f"{message_text[:60]}{'...' if len(message_text) > 60 else ''}"
                )""",
)

patch(
    "modules/service_plugins/webhook_service.py",
    """                sent = await self._send_dm(dm_to, message_text)
                if not sent:
                    self.logger.error(
                        f"Webhook: failed to send DM to '{dm_to}' from {request.remote}"
                    )
                    return aio_web.Response(
                        status=500,
                        content_type="application/json",
                        text='{"error": "Failed to send message"}',
                    )
                self.logger.info(
                    f"Webhook: sent DM to {dm_to} from {request.remote}: "
                    f"{message_text[:60]}{'...' if len(message_text) > 60 else ''}"
                )""",
    """                for chunk in message_chunks:
                    sent = await self._send_dm(dm_to, chunk)
                    if not sent:
                        self.logger.error(
                            f"Webhook: failed to send DM to '{dm_to}' from {request.remote}"
                        )
                        return aio_web.Response(
                            status=500,
                            content_type="application/json",
                            text='{"error": "Failed to send message"}',
                        )
                self.logger.info(
                    f"Webhook: sent DM to {dm_to} from {request.remote} in "
                    f"{len(message_chunks)} part(s): "
                    f"{message_text[:60]}{'...' if len(message_text) > 60 else ''}"
                )""",
)
