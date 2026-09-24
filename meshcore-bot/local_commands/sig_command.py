#!/usr/bin/env python3
"""
'sig' command for the MeshCore Bot: how well your message came in, with a plain verdict.

  sig      e.g. "Signaal: SNR 7,5 dB, RSSI -97 dBm, 3 hops (laatste repeater naar de bot): goed"

Useful for antenna work: send 'sig', move the antenna, send it again. With 0 hops the numbers are about your own
radio and antenna; with hops they are about the last repeater before the bot, which the reply says.

Verdict by SNR (LoRa can still decode well below 0 dB; the limit for SF8 is about -10 dB):
  >= 5 dB goed, >= -5 dB redelijk, >= -10 dB zwak, lower: heel zwak.
"""

from typing import Any

from ..models import MeshMessage
from ..utils import message_hop_count
from .base_command import BaseCommand


def verdict_key(snr: float) -> str:
    if snr >= 5:
        return "good"
    if snr >= -5:
        return "fair"
    if snr >= -10:
        return "weak"
    return "very_weak"


def _num(value: float) -> str:
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


class SigCommand(BaseCommand):
    """Signal of your message (SNR, RSSI, hops) with a verdict."""

    name = "sig"
    keywords = ["sig", "signaal"]
    description = "Signaal van je bericht: SNR, RSSI en hops, met een oordeel (handig bij antenne-tuning)"
    category = "meshcore_info"

    short_description = "Signaal van je bericht (SNR/RSSI) met oordeel"
    usage = "sig"
    examples = ["sig"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.sig_enabled = self.get_config_value("Sig_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.sig_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.sig.help")

    def build(self, message: MeshMessage) -> str:
        if message.snr is None:
            return self.translate("commands.sig.no_data")
        hops = message_hop_count(message)
        snr = float(message.snr)
        rssi = self.translate("commands.sig.rssi", rssi=int(message.rssi)) if message.rssi is not None else ""
        if hops is None:
            where = ""
        elif hops == 0:
            where = self.translate("commands.sig.direct")
        else:
            where = self.translate("commands.sig.via", hops=hops)
        return self.translate("commands.sig.reply", snr=_num(snr), rssi=rssi, where=where,
                              verdict=self.translate(f"commands.sig.verdict.{verdict_key(snr)}"))

    async def execute(self, message: MeshMessage) -> bool:
        try:
            return await self.send_response(message, self.build(message))
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error executing sig command: {e}")
            return await self.send_response(message, self.translate("commands.sig.error", error=str(e)))
