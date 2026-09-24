"""Home Assistant bridge service plugin.

De bot praat rechtstreeks met meshcore-proxy (buiten meshcore-ha om), dus
zijn eigen kanaalantwoorden komen nooit op meshcore-ha's event bus terecht
en worden daardoor niet door het meshcore_chat-paneel gelogd. Deze service
mirrort elk uitgaand kanaalbericht naar een HA-webhook; een automation aan
de HA-kant zet dat om in een synthetisch `meshcore_message`-event (hetzelfde
event dat meshcore-ha zelf al vuurt), zodat meshcore_chat het opslaat alsof
het gewoon van meshcore-ha kwam. Er gaat geen extra pakket de lucht in -
puur een side-channel notificatie over HTTP.

Config (config.ini):

    [HomeAssistantBridge]
    enabled = true
    webhook_url = http://localhost:8123/api/webhook/meshcore_bot_relay
    # optional: first 6 hex chars of the radio's public key (auto-derived if empty)
    node_prefix =
"""
from __future__ import annotations

from typing import Any, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover - aiohttp is a bot dependency, but stay defensive
    aiohttp = None  # type: ignore[assignment]

from .base_service import BaseServicePlugin

# meshcore-ha's node prefix, part of the fixed entity_id pattern it uses for
# every per-channel binary_sensor: binary_sensor.meshcore_<prefix>_ch_<idx>_messages.
# Derived from this node's public key, so it only changes if the physical
# radio is replaced. Every channel follows this same pattern (confirmed for
# channels 0/1/2/3/4/5/8 so far), so the entity_id is computed from
# channel_idx directly instead of a hand-maintained per-channel map - a
# newly added channel (e.g. #p2000-zl on index 5) works immediately without
# an edit here, whereas the old static map silently dropped any channel it
# didn't already know about (that's what caused #p2000/#p2000-zl messages to
# never reach meshcore_chat).
def _entity_id_for_channel(node_prefix: str, channel_idx: int) -> str:
    return f"binary_sensor.meshcore_{node_prefix}_ch_{channel_idx}_messages"


class HomeAssistantBridgeService(BaseServicePlugin):
    config_section = "HomeAssistantBridge"

    # Settings card on the dashboard's Plugins page (the add-on options for this moved here in 2.7.0).
    settings_schema = [
        {"key": "webhook_url", "label": "Home Assistant webhook URL", "type": "str", "default": "",
         "help": ("Makes the bot's own replies show up in the MeshCore Chat panel: "
                  "http://127.0.0.1:8123/api/webhook/meshcore_bot_relay (needs the relay automation from the documentation).")},
        {"key": "node_prefix", "label": "Node prefix", "type": "str", "default": "",
         "pattern": "([0-9a-fA-F]{2,12})?",
         "help": "Optional. Empty = the first 6 characters of the radio's public key, as meshcore-ha uses."},
    ]
    description = "Mirrors bot channel and direct-message/room replies into Home Assistant's MeshCore Chat panel"

    def __init__(self, bot: Any):
        super().__init__(bot)
        section = self.config_section
        cfg = bot.config
        self.webhook_url: str = (
            cfg.get(section, "webhook_url", fallback="").strip()
            if cfg.has_section(section)
            else ""
        )
        # Empty = derive from the radio's own public key when the first message
        # is mirrored (meshcore-ha names its entities after the first 6 hex
        # characters of the node's public key).
        self.node_prefix: str = (
            cfg.get(section, "node_prefix", fallback="").strip().lower()
            if cfg.has_section(section)
            else ""
        )
        self._session: Optional["aiohttp.ClientSession"] = None

    def _resolve_node_prefix(self) -> str:
        if self.node_prefix:
            return self.node_prefix
        self_info = getattr(getattr(self.bot, "meshcore", None), "self_info", None)
        key = ""
        if isinstance(self_info, dict):
            key = self_info.get("public_key", "") or ""
        elif self_info is not None:
            key = getattr(self_info, "public_key", "") or ""
        if key:
            self.node_prefix = key[:6].lower()
            self.logger.info(
                "HomeAssistantBridge: node_prefix afgeleid van de radio: %s", self.node_prefix
            )
        return self.node_prefix

    async def start(self) -> None:
        if not self.webhook_url:
            self.logger.warning(
                "HomeAssistantBridge: geen webhook_url ingesteld, service blijft uit"
            )
            self.enabled = False
            return
        if aiohttp is None:
            self.logger.warning(
                "HomeAssistantBridge: aiohttp niet beschikbaar, kan niet naar Home Assistant posten"
            )
            self.enabled = False
            return
        self._session = aiohttp.ClientSession()
        self.bot.channel_sent_listeners.append(self._on_channel_sent)
        # DM hook added by patch_dm_sent_listeners.py (upstream has none): replies
        # to DMs, and thus everything the bot says in a room server.
        if not hasattr(self.bot, "dm_sent_listeners"):
            self.bot.dm_sent_listeners = []
        self.bot.dm_sent_listeners.append(self._on_dm_sent)
        self._running = True

    async def stop(self) -> None:
        listeners = getattr(self.bot, "channel_sent_listeners", None)
        if listeners is not None and self._on_channel_sent in listeners:
            listeners.remove(self._on_channel_sent)
        dm_listeners = getattr(self.bot, "dm_sent_listeners", None)
        if dm_listeners is not None and self._on_dm_sent in dm_listeners:
            dm_listeners.remove(self._on_dm_sent)
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._running = False

    async def _on_channel_sent(self, event: Any, _unused: Any) -> None:
        if self._session is None:
            return
        payload = event.payload
        channel_idx = payload.get("channel_idx")
        text = payload.get("text", "")
        # channel_manager.py formats this as "{bot_name}: {content}".
        sender, sep, message = text.partition(": ")
        if not sep:
            sender, message = self.bot.config.get(
                "Bot", "bot_name", fallback="Bot"
            ), text

        if channel_idx is None:
            return
        node_prefix = self._resolve_node_prefix()
        if not node_prefix:
            self.logger.warning(
                "HomeAssistantBridge: node_prefix onbekend (stel home_assistant.node_prefix in), bericht niet gespiegeld"
            )
            return
        entity_id = _entity_id_for_channel(node_prefix, channel_idx)
        channel_manager = getattr(self.bot, "channel_manager", None)
        channel_name = (
            channel_manager.get_channel_name(channel_idx)
            if channel_manager is not None
            else str(channel_idx)
        )

        body = {
            "entity_id": entity_id,
            "channel_idx": channel_idx,
            "channel": channel_name,
            "sender_name": sender,
            "message": message,
            "message_type": "channel",
            "outgoing": True,
        }
        await self._post(body)

    async def _on_dm_sent(self, event: Any, _unused: Any) -> None:
        if self._session is None:
            return
        payload = event.payload
        contact_key = (payload.get("contact_public_key") or "").lower()
        if len(contact_key) < 12:
            return
        node_prefix = self._resolve_node_prefix()
        if not node_prefix:
            self.logger.warning(
                "HomeAssistantBridge: node_prefix onbekend (stel home_assistant.node_prefix in), DM niet gespiegeld"
            )
            return
        # Same shape as the meshcore_message event meshcore-ha fires for an
        # outgoing direct message (custom_components/meshcore/logbook.py).
        body = {
            "entity_id": f"binary_sensor.meshcore_{node_prefix}_{contact_key[:6]}_messages",
            "sender_name": self.bot.config.get("Bot", "bot_name", fallback="Bot"),
            "receiver_name": payload.get("contact_name", ""),
            "pubkey_prefix": contact_key[:12],
            "message": payload.get("text", ""),
            "message_type": "direct",
            "outgoing": True,
        }
        await self._post(body)

    async def _post(self, body: dict) -> None:
        try:
            async with self._session.post(
                self.webhook_url, json=body, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status >= 300:
                    self.logger.warning(
                        "HomeAssistantBridge: webhook antwoordde met status %s", resp.status
                    )
        except Exception as exc:  # noqa: BLE001 - never let a bridge failure break bot replies
            self.logger.warning(
                "HomeAssistantBridge: webhook post mislukt: %s: %r", type(exc).__name__, exc
            )
