"""Tiny per-channel session store with a TTL.

Used by stateful mesh commands (poll/hangman/quiz) that need "one active
thing per channel, expires after N seconds, subsequent matching messages are
input for it". In-memory only - lost on bot restart, which is fine for these
short-lived, casual interactions (no need for sqlite/dependency overhead).

Each command instantiates its own ChannelSession so poll/hangman/quiz never
share or collide with each other's state.
"""

import time
from typing import Any, Optional


class ChannelSession:
    def __init__(self) -> None:
        self._sessions: dict[str, tuple[float, Any]] = {}

    def start(self, channel: str, data: Any, ttl_seconds: float) -> None:
        self._sessions[channel] = (time.time() + ttl_seconds, data)

    def get(self, channel: str) -> Optional[Any]:
        entry = self._sessions.get(channel)
        if entry is None:
            return None
        expires_at, data = entry
        if time.time() > expires_at:
            del self._sessions[channel]
            return None
        return data

    def end(self, channel: str) -> None:
        self._sessions.pop(channel, None)

    def is_active(self, channel: str) -> bool:
        return self.get(channel) is not None
