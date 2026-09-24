#!/usr/bin/env python3
"""
'buien' command for the MeshCore Bot: rain in the next 2 hours as a small timeline (Buienradar, NL and BE).

  buien [plaats]    e.g. "Buien Weert 14:05-16:05: ··▂▅█▃······ max 2,1 mm/u om 14:40"

One character per 10 minutes: · dry, ▂ light, ▃ moderate, ▅ heavy, ▇ very heavy, █ downpour (per 10 minutes the
heaviest of the two 5-minute values). Without a place: the sender's position (when the bot knows it from their
advert), else the bot's own position. The data is Buienradar's free text forecast
(gpsgadget.buienradar.nl/data/raintext); it only covers the Netherlands and Belgium. Upstream's 'rain' does the
same for anywhere in the world, as text.
"""

import asyncio
import math
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

from ..mesh_community import fit_bytes, split_args
from ..models import MeshMessage
from .base_command import BaseCommand

URL = "https://gpsgadget.buienradar.nl/data/raintext"
SLOTS = 12


def mm_per_hour(value: int) -> float:
    """Buienradar's 0-255 value to mm/h (their formula: 10^((value-109)/32)); 0 means dry."""
    return 0.0 if value <= 0 else round(10 ** ((value - 109) / 32), 2)


def symbol(mm: float) -> str:
    if mm < 0.1:
        return "·"
    if mm < 0.5:
        return "▂"
    if mm < 1.0:
        return "▃"
    if mm < 2.5:
        return "▅"
    if mm < 5.0:
        return "▇"
    return "█"


def parse_raintext(text: str) -> list:
    """[(HH:MM, mm/h)] from lines like '077|14:05'."""
    out = []
    for line in (text or "").splitlines():
        value, _, clock = line.strip().partition("|")
        if value.strip().isdigit() and len(clock.strip()) == 5:
            out.append((clock.strip(), mm_per_hour(int(value))))
    return out


def timeline(rows: list) -> tuple:
    """(symbols, first time, last time, max mm/h, time of max) over 10-minute slots."""
    slots = []
    for i in range(0, min(len(rows), SLOTS * 2), 2):
        pair = rows[i:i + 2]
        slots.append(max(pair, key=lambda r: r[1]))
    peak = max(slots, key=lambda r: r[1]) if slots else ("", 0.0)
    return "".join(symbol(mm) for _t, mm in slots), rows[0][0], rows[min(len(rows), SLOTS * 2) - 1][0], peak[1], peak[0]


def _num(value: float) -> str:
    return (f"{value:.1f}" if value < 10 else f"{value:.0f}").replace(".", ",")


class BuienCommand(BaseCommand):
    """Rain in the next 2 hours as a timeline (Buienradar)."""

    name = "buien"
    keywords = ["buien", "buienradar"]
    description = "Regen de komende 2 uur als tijdlijn per 10 minuten (Buienradar, NL/BE)"
    category = "weather"
    requires_internet = True

    short_description = "Regen komende 2 uur (Buienradar)"
    usage = "buien [plaats]"
    examples = ["buien", "buien Weert"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.buien_enabled = self.get_config_value("Buien_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.buien_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.buien.help")

    def _locate(self, place: str, message: MeshMessage) -> tuple:
        """(lat, lon, name) or (None, None, error key)."""
        from ..location import resolve_with_message_fallbacks
        found = resolve_with_message_fallbacks(self.bot, place or None, message)
        if found.lat is None or found.lon is None:
            return None, None, "commands.buien.no_place" if place else "commands.buien.no_position"
        name = place.title() if place else (found.display_name or "")
        return found.lat, found.lon, (name.split(",")[0].strip() or self.translate("commands.buien.here"))

    @staticmethod
    def _fetch(lat: float, lon: float) -> str:
        response = requests.get(URL, params={"lat": f"{lat:.2f}", "lon": f"{lon:.2f}"}, timeout=10)
        response.raise_for_status()
        return response.text

    def render(self, rows: list, where: str, max_bytes: int) -> str:
        if not rows:
            return self.translate("commands.buien.no_data")
        marks, start, end, peak, at = timeline(rows)
        if peak < 0.1:
            return fit_bytes(self.translate("commands.buien.dry", place=where, end=end), max_bytes)
        return fit_bytes(self.translate("commands.buien.reply", place=where, start=start, end=end, line=marks,
                                        max=_num(peak), at=at), max_bytes)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            if requests is None:
                return await self.send_response(message, self.translate("commands.buien.no_data"))
            place = split_args(self, message)
            lat, lon, where = await asyncio.to_thread(self._locate, place, message)
            if lat is None:
                return await self.send_response(message, self.translate(where, place=place))
            if not (math.isfinite(lat) and 49.0 <= lat <= 54.5 and 2.0 <= lon <= 7.8):
                return await self.send_response(message, self.translate("commands.buien.outside"))
            rows = parse_raintext(await asyncio.to_thread(self._fetch, lat, lon))
            return await self.send_response(message, self.render(rows, where, self.get_max_message_length(message)))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing buien command: {e}")
            return await self.send_response(message, self.translate("commands.buien.error", error=str(e)))
