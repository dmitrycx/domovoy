"""Domain models for Domovoy (SPEC.md §7)."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Status(enum.StrEnum):
    OPEN = "open"
    PROGRESS = "progress"
    DONE = "done"
    WONTFIX = "wontfix"


@dataclass(slots=True)
class Request:
    id: int
    group_chat_id: int
    card_chat_id: int | None
    card_msg_id: int | None
    author_id: int
    author_name: str
    description: str
    photo_file_id: str | None
    status: Status
    owner: str | None
    created_at: str  # ISO-8601 UTC
    updated_at: str  # ISO-8601 UTC
    deleted: bool
    votes: int = 0
