#!/usr/bin/env python3
"""
'kenteken' command for the MeshCore Bot.
Looks up a Dutch license plate via the free RDW open data API (the same
public dataset ovi.rdw.nl uses) - no key required, no owner/personal info
included (RDW deliberately excludes that from the open dataset).

Deliberately minimal per user preference: merk+handelsbenaming, bouwjaar,
eerste kleur, brandstoftype, cilinderinhoud+vermogen, topsnelheid, APK
vervaldatum - just enough to fit comfortably in a single mesh message (no
chunking needed). Fields the API doesn't return (or returns as a bogus
"0") are simply left out rather than shown as empty/zero.

Only Dutch plates: Belgium (DIV) and Germany (KBA) have no free open register. A Belgian plate (1-ABC-234, seven
characters, which no Dutch plate has) or a plate typed with a country word first ("kenteken be ...", "kenteken d
...") gets that answer straight away; a plate that looks German (M-AB 1234) gets it when the RDW does not know it.
"""

import re
from datetime import date, datetime
from typing import Any, Optional

import aiohttp

from ..models import MeshMessage
from .base_command import BaseCommand

_VEHICLE_URL = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"
_FUEL_URL = "https://opendata.rdw.nl/resource/8ys7-d773.json"

_BELGIAN = re.compile(r"^[1-9][A-Z]{3}\d{3}$")                                   # 1-ABC-234 (since 2010)
_GERMAN = re.compile(r"^[A-ZÄÖÜ]{1,3}[- ][A-Z]{1,2}[- ]?\d{1,4}[EH]?$", re.IGNORECASE)  # M-AB 1234, B AB 123E
_COUNTRY_WORDS = {"be": "be", "b": "be", "belgie": "be", "belgië": "be", "belgisch": "be",
                  "de": "de", "d": "de", "duits": "de", "duitsland": "de", "deutschland": "de"}


def foreign_country(raw: str) -> str:
    """'be' / 'de' when the input is clearly a Belgian or German plate (or starts with a country word), else ''."""
    words = raw.strip().split(maxsplit=1)
    if len(words) == 2 and words[0].lower() in _COUNTRY_WORDS:
        return _COUNTRY_WORDS[words[0].lower()]
    if _BELGIAN.match(re.sub(r"[^A-Za-z0-9]", "", raw).upper()):
        return "be"
    return ""


def looks_german(raw: str) -> bool:
    return bool(_GERMAN.match(raw.strip()))


class KentekenCommand(BaseCommand):
    """Looks up a Dutch license plate via the RDW open data API."""

    name = "kenteken"
    keywords = ["kenteken"]
    description = "Kentekencheck via RDW open data (usage: kenteken hdj60r)"
    category = "general"
    requires_internet = True

    short_description = "Kentekencheck (RDW)"
    usage = "kenteken <plaat>"
    examples = ["kenteken hdj-60-r", "kenteken 1-abc-23"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.kenteken_enabled = self.get_config_value(
            "Kenteken_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.kenteken_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return (
            "Zoekt een kenteken op via RDW open data: merk+model, bouwjaar, kleur, "
            "brandstof, cilinderinhoud/vermogen, topsnelheid, APK-vervaldatum. "
            "Geen persoonsgegevens."
        )

    @staticmethod
    def _normalize_plate(raw: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", raw).upper()

    @staticmethod
    def _bouwjaar(value: Optional[str]) -> Optional[str]:
        if not value or len(value) != 8:
            return None
        try:
            datetime.strptime(value, "%Y%m%d")
        except ValueError:
            return None
        return value[:4]

    def _format_apk(self, value: Optional[str]) -> Optional[str]:
        if not value or len(value) != 8:
            return None
        try:
            dt = datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            return None
        formatted = dt.strftime("%d-%m-%Y")
        days = (dt - date.today()).days
        if days < 0:
            return self.translate("commands.kenteken.apk_expired", date=formatted)
        if days <= 30:
            return self.translate("commands.kenteken.apk_soon", date=formatted, days=days)
        return self.translate("commands.kenteken.apk", date=formatted)

    @staticmethod
    def _get(d: dict, key: str) -> Optional[str]:
        """Return the value for key, or None if missing/empty - so callers can
        skip the field entirely instead of showing a blank/None."""
        value = d.get(key)
        if value is None:
            return None
        value = str(value).strip()
        return value if value else None

    async def _fetch_json(self, session: aiohttp.ClientSession, url: str, plate: str) -> list:
        try:
            async with session.get(
                url, params={"kenteken": plate}, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return []
                return await resp.json()
        except Exception as e:
            self.logger.warning(f"kenteken: fout bij ophalen {url}: {e}")
            return []

    def _build_message(self, plate: str, v: dict, f: dict) -> str:
        merk_model = " ".join(
            x for x in (self._get(v, "merk"), self._get(v, "handelsbenaming")) if x
        )
        bits: list[Optional[str]] = [
            merk_model or None,
            self._bouwjaar(self._get(v, "datum_eerste_toelating")),
            self._get(v, "eerste_kleur"),
            self._get(f, "brandstof_omschrijving") if f else None,
        ]

        cc = self._get(v, "cilinderinhoud")
        kw = self._get(f, "nettomaximumvermogen") if f else None
        try:
            cc = None if cc is not None and float(cc) == 0 else cc
        except ValueError:
            pass
        try:
            kw = None if kw is not None and float(kw) == 0 else kw
        except ValueError:
            pass
        if cc and kw:
            bits.append(f"{cc}cc/{kw}kW")
        elif cc:
            bits.append(f"{cc}cc")
        elif kw:
            bits.append(f"{kw}kW")

        topsnelheid = self._get(v, "maximale_constructiesnelheid")
        try:
            if topsnelheid is not None and float(topsnelheid) != 0:
                bits.append(f"{topsnelheid}km/u")
        except ValueError:
            pass

        bits.append(self._format_apk(self._get(v, "vervaldatum_apk")))

        clean_bits = [b for b in bits if b]
        return f"{plate}: " + " | ".join(clean_bits)

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip()
            if content.lower().startswith("kenteken"):
                content = content[len("kenteken"):].strip()

            if not content:
                return await self.send_response(message, self.translate("commands.kenteken.usage"))

            country = foreign_country(content)
            if country:
                key = "commands.kenteken.foreign_be" if country == "be" else "commands.kenteken.foreign_de"
                return await self.send_response(message, self.translate(key))
            plate = self._normalize_plate(content)
            if not plate:
                return await self.send_response(message, self.translate("commands.kenteken.invalid"))

            async with aiohttp.ClientSession() as session:
                vehicle_rows = await self._fetch_json(session, _VEHICLE_URL, plate)
                fuel_rows = await self._fetch_json(session, _FUEL_URL, plate)

            if not vehicle_rows:
                if looks_german(content):
                    return await self.send_response(message, self.translate("commands.kenteken.foreign_de"))
                return await self.send_response(
                    message, self.translate("commands.kenteken.not_found", plate=content)
                )

            response = self._build_message(plate, vehicle_rows[0], fuel_rows[0] if fuel_rows else {})
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing kenteken command: {e}")
            return await self.send_response(message, self.translate("commands.kenteken.error", error=str(e)))
