#!/usr/bin/env python3
"""
'weerwaarschuwing' command for the MeshCore Bot.
Latest official KNMI weather warning text (code geel/oranje/rood, incl.
gladheid/ijzel - no separate 'gladheid' command, KNMI already categorizes
that as a warning type here) via the KNMI Data Platform Open Data API.

The API key is hardcoded rather than an add-on option: same reasoning as
the dashboard_token in patch_webviewer.py - Supervisor only re-reads a local
add-on's config.yaml schema on specific reload events, not on every
`ha addons rebuild`, so a brand new option key would silently fail to
persist via the Configuration tab/API until a full Supervisor restart.
Registered (non-expiring) key from https://developer.dataplatform.knmi.nl.
"""

from typing import Any, Optional

import aiohttp

from ..models import MeshMessage
from .base_command import BaseCommand

# KNMI's public anonymous open-data key (published on developer.dataplatform.knmi.nl), not a personal one; KNMI replaces it now and then.
_KNMI_API_KEY = "eyJvcmciOiI1ZTU1NGUxOTI3NGE5NjAwMDEyYTNlYjEiLCJpZCI6IjI0YmYxOTJlNWIzYjRjYjQ5ZTQ3MGI2ZWI0MGQwYmZlIiwiaCI6Im11cm11cjEyOCJ9"
_DATASET_URL = (
    "https://api.dataplatform.knmi.nl/open-data/v1/datasets/"
    "waarschuwingen_nederland_48h/versions/1.0/files"
)


class WeerwaarschuwingCommand(BaseCommand):
    """Shows the latest official KNMI weather warning text."""

    name = "weerwaarschuwing"
    keywords = ["weerwaarschuwing", "gladheid"]
    description = "Actuele officiële KNMI-weerwaarschuwing"
    category = "general"
    requires_internet = True

    short_description = "Actuele KNMI-weerwaarschuwing"
    usage = "weerwaarschuwing"
    examples = ["weerwaarschuwing"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.weerwaarschuwing_enabled = self.get_config_value(
            "Weerwaarschuwing_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.weerwaarschuwing_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "De meest recente officiële KNMI-weerwaarschuwing (incl. code geel/oranje/rood, gladheid/ijzel)."

    async def _latest_txt_filename(self, session: aiohttp.ClientSession) -> Optional[str]:
        params = {"maxKeys": 10, "orderBy": "created", "sorting": "desc"}
        headers = {"Authorization": _KNMI_API_KEY}
        async with session.get(
            _DATASET_URL, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        for f in data.get("files", []):
            name = f.get("filename", "")
            if name.endswith(".txt"):
                return name
        return None

    async def execute(self, message: MeshMessage) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                filename = await self._latest_txt_filename(session)
                if not filename:
                    return await self.send_response(
                        message, self.translate("commands.weerwaarschuwing.no_file")
                    )

                headers = {"Authorization": _KNMI_API_KEY}
                async with session.get(
                    f"{_DATASET_URL}/{filename}/url",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return await self.send_response(
                            message, self.translate("commands.weerwaarschuwing.no_link")
                        )
                    url_data = await resp.json()
                download_url = url_data.get("temporaryDownloadUrl")
                if not download_url:
                    return await self.send_response(message, self.translate("commands.weerwaarschuwing.no_link"))

                async with session.get(
                    download_url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return await self.send_response(
                            message, self.translate("commands.weerwaarschuwing.download_error")
                        )
                    text = (await resp.text()).strip()

            if not text:
                return await self.send_response(message, self.translate("commands.weerwaarschuwing.empty"))

            max_len = self.get_max_message_length(message)
            if len(text.encode("utf-8")) <= max_len:
                return await self.send_response(message, text)

            # Longer real warnings: split on blank lines into mesh-sized chunks.
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            chunks: list[str] = []
            current = ""
            for para in paragraphs:
                candidate = f"{current}\n\n{para}" if current else para
                if current and len(candidate.encode("utf-8")) > max_len:
                    chunks.append(current)
                    current = para
                else:
                    current = candidate
            if current:
                chunks.append(current)

            return await self.send_response_chunked(message, chunks)
        except Exception as e:
            self.logger.error(f"Error executing weerwaarschuwing command: {e}")
            return await self.send_response(
                message, self.translate("commands.weerwaarschuwing.error", error=str(e))
            )
