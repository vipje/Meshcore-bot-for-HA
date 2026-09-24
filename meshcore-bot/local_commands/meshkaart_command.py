#!/usr/bin/env python3
"""
'meshkaart' command for the MeshCore Bot: how big the mesh is that the bot hears.

  meshkaart   e.g. "Mesh 24u: 42 nodes (30 companions, 10 repeaters, 2 rooms), 28 met positie | 7d: 88 | ooit: 310"

Counts from upstream's contact tracking (complete_contact_tracking: every advert the bot heard, with role, position
and last-heard time). The map itself is the Mesh page of the bot's dashboard; this is the summary for the radio.
"""

from typing import Any

from ..mesh_community import table_exists
from ..models import MeshMessage
from .base_command import BaseCommand

ROLES = {"companion": "companion", "repeater": "repeater", "roomserver": "room", "sensor": "sensor"}


class MeshkaartCommand(BaseCommand):
    """Size of the mesh the bot hears: nodes per role, last 24h, 7 days and ever."""

    name = "meshkaart"
    keywords = ["meshkaart", "nodes"]
    description = "Hoeveel nodes, repeaters en rooms de bot hoort (24u, 7 dagen, ooit)"
    category = "meshcore_info"

    short_description = "Aantal nodes/repeaters dat de bot hoort"
    usage = "meshkaart"
    examples = ["meshkaart"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.mk_enabled = self.get_config_value("Meshkaart_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.mk_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.meshkaart.help")

    def counts(self) -> dict:
        out = {"roles": {}, "day": 0, "located": 0, "week": 0, "ever": 0}
        with self.bot.db_manager.connection() as conn:
            if not table_exists(conn, "complete_contact_tracking"):
                return out
            # Same window test as upstream's own counts (maintenance.py, repeater_manager.py).
            day, week = "datetime('now', '-1 day')", "datetime('now', '-7 days')"
            for role, n in conn.execute(
                    "SELECT LOWER(role), COUNT(DISTINCT public_key) FROM complete_contact_tracking WHERE last_heard >= " + day + " GROUP BY LOWER(role)").fetchall():
                key = ROLES.get(role or "", "other")
                out["roles"][key] = out["roles"].get(key, 0) + n
            out["day"] = sum(out["roles"].values())
            out["located"] = conn.execute(
                """SELECT COUNT(DISTINCT public_key) FROM complete_contact_tracking WHERE last_heard >= """ + day + """
                   AND latitude IS NOT NULL AND longitude IS NOT NULL AND latitude != 0 AND longitude != 0""").fetchone()[0]
            out["week"] = conn.execute("SELECT COUNT(DISTINCT public_key) FROM complete_contact_tracking WHERE last_heard >= " + week).fetchone()[0]
            out["ever"] = conn.execute("SELECT COUNT(DISTINCT public_key) FROM complete_contact_tracking").fetchone()[0]
        return out

    def build(self) -> str:
        c = self.counts()
        if not c["ever"]:
            return self.translate("commands.meshkaart.no_data")
        parts = [self.translate(f"commands.meshkaart.role.{r}", n=c["roles"][r])
                 for r in ("companion", "repeater", "room", "sensor", "other") if c["roles"].get(r)]
        return self.translate("commands.meshkaart.reply", day=c["day"], roles=", ".join(parts) or "-",
                              located=c["located"], week=c["week"], ever=c["ever"])

    async def execute(self, message: MeshMessage) -> bool:
        try:
            return await self.send_response(message, self.build())
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing meshkaart command: {e}")
            return await self.send_response(message, self.translate("commands.meshkaart.error", error=str(e)))
