"""Env-var configuration (SPEC.md §10)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DIGEST_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ConfigError(Exception):
    """Invalid or missing configuration."""


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    coordinator_ids: frozenset[int]
    db_path: str
    digest_time: str  # "HH:MM", local to `tz`
    tz: str

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "Config":
        token = env.get("BOT_TOKEN", "").strip()
        if not token:
            raise ConfigError("BOT_TOKEN is required")

        raw_ids = env.get("COORDINATOR_IDS", "")
        coordinator_ids = set()
        for part in raw_ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                coordinator_ids.add(int(part))
            except ValueError:
                raise ConfigError(f"COORDINATOR_IDS contains a non-numeric id: {part!r}")

        digest_time = env.get("DIGEST_TIME", "09:00").strip()
        if not _DIGEST_TIME_RE.match(digest_time):
            raise ConfigError(f"DIGEST_TIME must be HH:MM, got {digest_time!r}")

        tz = env.get("TZ", "UTC").strip()
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise ConfigError(f"TZ is not a valid IANA timezone: {tz!r}")

        return cls(
            bot_token=token,
            coordinator_ids=frozenset(coordinator_ids),
            db_path=env.get("DB_PATH", "data/domovoy.db").strip(),
            digest_time=digest_time,
            tz=tz,
        )

    def is_coordinator(self, user_id: int) -> bool:
        return user_id in self.coordinator_ids
