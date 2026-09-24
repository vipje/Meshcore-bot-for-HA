#!/usr/bin/env python3
"""
'rptr' command for the MeshCore Bot: the status of your repeater, from Home Assistant.

  rptr                 battery, uptime, airtime and neighbour count of the repeater(s), and how old that data is
  rptr buren           the neighbours with the best signal first
  rptr accu [24u|7d]   the battery over the last day (or hours/days): now, lowest, highest and the trend
  rptr list            every repeater and room server meshcore-ha knows (with the prefix for the HARepeater card)
  rptr <name or key>   pick one repeater when there are several

Everything comes from the HARepeater service, which only reads Home Assistant: this command never sends
anything over the radio to the repeater, so it costs no airtime and shows what meshcore-ha last received.
"""

from typing import Any

import re

from ..ha_repeater_parser import battery_text, fit, neighbours_text, summary
from ..models import MeshMessage
from .base_command import BaseCommand

NEIGHBOUR_WORDS = {"buren", "buur", "neighbours", "neighbors", "neighbour", "neighbor"}
LIST_WORDS = {"list", "lijst"}
ACCU_WORDS = {"accu", "batterij", "battery", "bat"}
PERIOD = re.compile(r"^(\d{1,3})([uhd])$")
MAX_BYTES = 130


class RptrCommand(BaseCommand):
    """Repeater status from Home Assistant."""

    name = "rptr"
    keywords = ["rptr"]
    description = "Batterij, uptime, airtime en buren van de repeater (uit Home Assistant)"
    category = "general"

    short_description = "Status van de repeater"
    usage = "rptr [buren|accu|list|naam]"
    examples = ["rptr", "rptr buren", "rptr accu", "rptr accu 7d", "rptr list"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        # Only on when the Home Assistant repeater link is on too: without meshcore-ha there is nothing to show, and
        # a switched-off command is left out of 'help' (and says it is off when typed anyway).
        self.rptr_enabled = (self.get_config_value("Rptr_Command", "enabled", fallback=True, value_type="bool")
                             and self.get_config_value("HARepeater", "enabled", fallback=False, value_type="bool"))

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.rptr_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return "rptr toont batterij, uptime, airtime en buren van de repeater; rptr buren = de buren; rptr accu [7d] = het verloop van de accu; rptr list = alle repeaters."

    def _arguments(self, message: MeshMessage) -> list:
        tokens = (message.content or "").split()
        for i, token in enumerate(tokens):
            if token.lstrip("!/").lower() in self.keywords:
                return tokens[i + 1:]
        return []

    async def execute(self, message: MeshMessage) -> bool:
        service = getattr(self.bot, "services", {}).get("harepeater")
        if service is None:
            return await self.send_response(message, self.translate("commands.rptr.no_service"))
        try:
            words = [w for w in self._arguments(message)]
            lower = [w.lower() for w in words]
            if not service.last_read:
                why = f" ({service.last_error})" if service.last_error else ""
                return await self.send_response(
                    message, fit(self.translate("commands.rptr.no_ha_data", why=why), MAX_BYTES)
                )

            if any(w in LIST_WORDS for w in lower):
                found = sorted(service.repeaters.values(), key=lambda r: r["name"].lower())
                if not found:
                    return await self.send_response(message, self.translate("commands.rptr.no_repeaters"))
                chosen = {r["prefix"] for r in service.current("")}
                items = [
                    f"{r['prefix']} {r['name']}" + ("" if r["prefix"] in chosen else self.translate("commands.rptr.not_tracked"))
                    for r in found
                ]
                return await self.send_response_chunked(message, self._pack(items, self.translate("commands.rptr.repeaters_header")))

            wants_neighbours = any(w in NEIGHBOUR_WORDS for w in lower)
            wants_battery = any(w in ACCU_WORDS for w in lower)
            hours = 24
            for w in lower:
                m = PERIOD.match(w)
                if m:
                    hours = max(1, min(720, int(m.group(1)) * (24 if m.group(2) == "d" else 1)))
            selector = " ".join(w for w in words if w.lower() not in NEIGHBOUR_WORDS | ACCU_WORDS and not PERIOD.match(w.lower()))
            chosen = service.current(selector)
            if not chosen:
                what = self.translate("commands.rptr.for_selector", selector=selector) if selector else ""
                return await self.send_response(
                    message, fit(self.translate("commands.rptr.not_found", what=what), MAX_BYTES)
                )

            if wants_neighbours:
                return await self.send_response(message, neighbours_text(chosen[0], self.translate, MAX_BYTES))
            if wants_battery:
                rows = service.battery_history(chosen[0]["public_key"], hours)
                return await self.send_response(
                    message, battery_text(chosen[0]["name"], rows, hours, self.translate, service.low_mv)
                )
            lines = [fit(summary(r, self.translate), MAX_BYTES) for r in chosen]
            if len(lines) == 1:
                return await self.send_response(message, lines[0])
            return await self.send_response_chunked(message, lines[:3])
        except Exception as e:
            self.logger.error(f"Error executing rptr command: {e}")
            return await self.send_response(message, self.translate("commands.rptr.error", error=str(e)))

    @staticmethod
    def _pack(items: list, head: str) -> list:
        chunks, current = [], head
        for item in items:
            candidate = current + ("" if current == head else " | ") + item
            if len(candidate.encode("utf-8")) > MAX_BYTES and current != head:
                chunks.append(current)
                current = item
            else:
                current = candidate
        chunks.append(current)
        return [fit(c, MAX_BYTES) for c in chunks[:3]]
