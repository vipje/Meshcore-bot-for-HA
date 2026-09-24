#!/usr/bin/env python3
"""
'pad' command for the MeshCore Bot: the route your message took, in one short message.

  pad      e.g. "5 hops · 76 km · Horsth→YAGI?→Wester→Westdorf"

The long version is upstream's own 'path' command (one line per repeater, with confidence marks). This one packs
the same information into a single message: the hop count, the distance and the repeater names, shortened until it
fits. A '?' after a name means the repeater is a best guess (several repeaters share that prefix); an unknown repeater
shows its hex prefix.

Names and positions come from upstream's path command (its lookup in the bot's contact database, with its own
collision handling), so the two always agree. The distance is the sum sender -> each repeater -> the bot when every
position is known; when only the sender's and the bot's positions are known it is the straight line ("hemelsbreed").
Channel messages carry no public key, so the sender's position is looked up by name.
"""

import re
from typing import Any, Optional

from ..mesh_community import fit_bytes
from ..models import MeshMessage
from ..utils import calculate_distance, message_hop_count
from .base_command import BaseCommand

_HEX_TOKEN = re.compile(r"^[0-9a-fA-F]{2,6}$")


def node_ids_of(message: MeshMessage) -> Optional[list]:
    """The repeater prefixes of this message in travel order; [] for direct, None when unknown."""
    info = getattr(message, "routing_info", None)
    if isinstance(info, dict):
        if info.get("path_length", None) == 0:
            return []
        nodes = info.get("path_nodes") or []
        if nodes:
            return [str(n).upper() for n in nodes]
    path = (message.path or "").strip()
    if not path:
        return None
    if "Direct" in path or path.startswith("0 hops"):
        return []
    path = path.split(" via ROUTE_TYPE_")[0].split("(")[0]
    tokens = [t.strip() for t in path.split(",") if t.strip()]
    if tokens and all(_HEX_TOKEN.match(t) for t in tokens):
        return [t.upper() for t in tokens]
    return None


def short_names(names: list, max_bytes: int, arrow: str = "→") -> str:
    """Join route names with arrows, cutting each name shorter until the whole route fits."""
    for width in (14, 10, 8, 6, 5, 4, 3):
        parts = []
        for name, guess in names:
            base = name if len(name) <= width else name[:width].rstrip() + "·"
            parts.append(base + ("?" if guess else ""))
        text = arrow.join(parts)
        if len(text.encode("utf-8")) <= max_bytes:
            return text
    return fit_bytes(arrow.join(n[:3] for n, _g in names), max_bytes)


class PadCommand(BaseCommand):
    """The route of your message: hops, distance and repeater names in one message."""

    name = "pad"
    keywords = ["pad"]
    description = "De route van je bericht in één regel: hops, afstand en repeaters (lang: path)"
    category = "meshcore_info"

    short_description = "Route van je bericht: hops, km en repeaters"
    usage = "pad"
    examples = ["pad"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.pad_enabled = self.get_config_value("Pad_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.pad_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.pad.help")

    # ------------------------------------------------------------------ positions
    def _sender_position(self, message: MeshMessage) -> Optional[tuple]:
        with self.bot.db_manager.connection() as conn:
            if message.sender_pubkey:
                row = conn.execute(
                    """SELECT latitude, longitude FROM complete_contact_tracking WHERE public_key = ?
                       AND latitude IS NOT NULL AND longitude IS NOT NULL AND latitude != 0 AND longitude != 0
                       ORDER BY COALESCE(last_advert_timestamp, last_heard) DESC LIMIT 1""",
                    (message.sender_pubkey,)).fetchone()
                if row:
                    return float(row[0]), float(row[1])
            if message.sender_id:
                rows = conn.execute(
                    """SELECT latitude, longitude FROM complete_contact_tracking WHERE LOWER(name) = LOWER(?)
                       AND role NOT IN ('repeater', 'roomserver')
                       AND latitude IS NOT NULL AND longitude IS NOT NULL AND latitude != 0 AND longitude != 0
                       ORDER BY COALESCE(last_advert_timestamp, last_heard) DESC LIMIT 2""",
                    (message.sender_id,)).fetchall()
                if len(rows) == 1:          # two people with the same name: better no distance than a wrong one
                    return float(rows[0][0]), float(rows[0][1])
        return None

    def _bot_position(self) -> Optional[tuple]:
        try:
            lat = self.bot.config.getfloat("Bot", "bot_latitude", fallback=None)
            lon = self.bot.config.getfloat("Bot", "bot_longitude", fallback=None)
        except (ValueError, TypeError):
            return None
        if lat is None or lon is None or (lat == 0 and lon == 0):
            return None
        return lat, lon

    @staticmethod
    def _distance(chain: list) -> float:
        return sum(calculate_distance(a[0], a[1], b[0], b[1]) for a, b in zip(chain, chain[1:]))

    # ------------------------------------------------------------------ reply
    async def build(self, message: MeshMessage) -> str:
        node_ids = node_ids_of(message)
        hops = message_hop_count(message)
        if node_ids is None:
            return self.translate("commands.pad.no_path")
        if not node_ids:
            return self.translate("commands.pad.direct")
        hops = hops if isinstance(hops, int) and hops > 0 else len(node_ids)

        info: dict = {}
        path_cmd = getattr(getattr(self.bot, "command_manager", None), "commands", {}).get("path")
        if path_cmd is not None:
            try:
                info = await path_cmd._lookup_repeater_names(node_ids) or {}
            except Exception as e:  # noqa: BLE001
                self.logger.debug(f"pad: repeater lookup failed: {e}")

        names, positions, all_known = [], [], True
        for node in node_ids:
            item = info.get(node, {})
            if item.get("found") and not item.get("collision") and item.get("name"):
                guess = bool(item.get("geographic_guess") or item.get("graph_guess")) and float(item.get("confidence", 0) or 0) < 0.9
                names.append((str(item["name"]), guess))
                lat, lon = item.get("latitude"), item.get("longitude")
                if lat is None or lon is None or (lat == 0 and lon == 0):
                    all_known = False
                else:
                    positions.append((float(lat), float(lon)))
            else:
                names.append((node.lower(), bool(item.get("collision"))))
                all_known = False

        sender, own = self._sender_position(message), self._bot_position()
        distance = ""
        if sender and own and all_known:
            distance = self.translate("commands.pad.km_route", km=f"{self._distance([sender] + positions + [own]):.0f}")
        elif sender and own:
            distance = self.translate("commands.pad.km_straight", km=f"{self._distance([sender, own]):.0f}")

        head = self.translate("commands.pad.hop_one" if hops == 1 else "commands.pad.hops", hops=hops) + (f" · {distance}" if distance else "") + " · "
        budget = self.get_max_message_length(message) - len(head.encode("utf-8"))
        return head + short_names(names, max(12, budget))

    async def execute(self, message: MeshMessage) -> bool:
        try:
            return await self.send_response(message, await self.build(message))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing pad command: {e}")
            return await self.send_response(message, self.translate("commands.pad.error", error=str(e)))
