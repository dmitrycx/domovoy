"""SQLite data layer via aiosqlite (SPEC.md §7)."""

from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from domovoy.models import Request, Status

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    group_chat_id INTEGER NOT NULL,
    card_chat_id  INTEGER,
    card_msg_id   INTEGER,
    author_id     INTEGER NOT NULL,
    author_name   TEXT NOT NULL,
    description   TEXT NOT NULL,
    photo_file_id TEXT,
    status        TEXT NOT NULL DEFAULT 'open',
    owner         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS votes (
    request_id INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    PRIMARY KEY (request_id, user_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# requests.* plus the live vote count
_SELECT = """
SELECT r.*, (SELECT COUNT(*) FROM votes v WHERE v.request_id = r.id) AS votes
FROM requests r
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_request(row: aiosqlite.Row) -> Request:
    return Request(
        id=row["id"],
        group_chat_id=row["group_chat_id"],
        card_chat_id=row["card_chat_id"],
        card_msg_id=row["card_msg_id"],
        author_id=row["author_id"],
        author_name=row["author_name"],
        description=row["description"],
        photo_file_id=row["photo_file_id"],
        status=Status(row["status"]),
        owner=row["owner"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted=bool(row["deleted"]),
        votes=row["votes"],
    )


class Database:
    def __init__(self, path: str):
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected; call connect() first")
        return self._conn

    # -- requests ---------------------------------------------------------

    async def create_request(
        self,
        *,
        group_chat_id: int,
        author_id: int,
        author_name: str,
        description: str,
        photo_file_id: str | None,
        now: str | None = None,
    ) -> Request:
        now = now or utcnow()
        cursor = await self.conn.execute(
            """
            INSERT INTO requests
                (group_chat_id, author_id, author_name, description,
                 photo_file_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (group_chat_id, author_id, author_name, description,
             photo_file_id, Status.OPEN.value, now, now),
        )
        await self.conn.commit()
        request = await self.get_request(cursor.lastrowid)
        assert request is not None
        return request

    async def get_request(
        self, request_id: int, group_chat_id: int | None = None
    ) -> Request | None:
        """Fetch a request; with group_chat_id, only if it belongs to that chat."""
        query = _SELECT + "WHERE r.id = ? AND r.deleted = 0"
        params: tuple = (request_id,)
        if group_chat_id is not None:
            query += " AND r.group_chat_id = ?"
            params += (group_chat_id,)
        cursor = await self.conn.execute(query, params)
        row = await cursor.fetchone()
        return _row_to_request(row) if row else None

    async def set_card_ref(self, request_id: int, *, chat_id: int, msg_id: int) -> None:
        await self.conn.execute(
            "UPDATE requests SET card_chat_id = ?, card_msg_id = ? WHERE id = ?",
            (chat_id, msg_id, request_id),
        )
        await self.conn.commit()

    async def set_status(
        self, request_id: int, status: Status, *, now: str | None = None
    ) -> None:
        await self.conn.execute(
            "UPDATE requests SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, now or utcnow(), request_id),
        )
        await self.conn.commit()

    async def set_owner(
        self, request_id: int, owner: str, *, now: str | None = None
    ) -> None:
        await self.conn.execute(
            "UPDATE requests SET owner = ?, updated_at = ? WHERE id = ?",
            (owner, now or utcnow(), request_id),
        )
        await self.conn.commit()

    async def soft_delete(self, request_id: int) -> None:
        await self.conn.execute(
            "UPDATE requests SET deleted = 1, updated_at = ? WHERE id = ?",
            (utcnow(), request_id),
        )
        # data minimization: voter IDs serve no purpose once the request is gone
        await self.conn.execute(
            "DELETE FROM votes WHERE request_id = ?", (request_id,)
        )
        await self.conn.commit()

    async def migrate_chat(self, old_chat_id: int, new_chat_id: int) -> None:
        """Re-home requests after a group→supergroup migration (new chat id).

        card_chat_id is left untouched: message ids do not survive migration,
        so pointing card edits at the new chat could hit unrelated messages —
        a failed edit on the dead chat is caught and logged instead.
        """
        await self.conn.execute(
            "UPDATE requests SET group_chat_id = ? WHERE group_chat_id = ?",
            (new_chat_id, old_chat_id),
        )
        await self.conn.commit()

    # -- lists ------------------------------------------------------------

    async def list_open(self, group_chat_id: int) -> list[Request]:
        cursor = await self.conn.execute(
            _SELECT
            + """
            WHERE r.group_chat_id = ? AND r.deleted = 0 AND r.status IN (?, ?)
            ORDER BY votes DESC, r.id ASC
            """,
            (group_chat_id, Status.OPEN.value, Status.PROGRESS.value),
        )
        return [_row_to_request(row) for row in await cursor.fetchall()]

    async def list_done(self, group_chat_id: int, *, limit: int = 20) -> list[Request]:
        cursor = await self.conn.execute(
            _SELECT
            + """
            WHERE r.group_chat_id = ? AND r.deleted = 0 AND r.status IN (?, ?)
            ORDER BY r.updated_at DESC
            LIMIT ?
            """,
            (group_chat_id, Status.DONE.value, Status.WONTFIX.value, limit),
        )
        return [_row_to_request(row) for row in await cursor.fetchall()]

    async def oldest_open(self, group_chat_id: int, *, limit: int = 5) -> list[Request]:
        cursor = await self.conn.execute(
            _SELECT
            + """
            WHERE r.group_chat_id = ? AND r.deleted = 0 AND r.status IN (?, ?)
            ORDER BY r.created_at ASC, r.id ASC
            LIMIT ?
            """,
            (group_chat_id, Status.OPEN.value, Status.PROGRESS.value, limit),
        )
        return [_row_to_request(row) for row in await cursor.fetchall()]

    # -- votes ------------------------------------------------------------

    async def toggle_vote(self, request_id: int, user_id: int) -> tuple[bool, int]:
        """Add the user's vote, or remove it if present. Returns (voted, count)."""
        cursor = await self.conn.execute(
            "DELETE FROM votes WHERE request_id = ? AND user_id = ?",
            (request_id, user_id),
        )
        voted = cursor.rowcount == 0
        if voted:
            await self.conn.execute(
                "INSERT INTO votes (request_id, user_id) VALUES (?, ?)",
                (request_id, user_id),
            )
        await self.conn.commit()
        return voted, await self.vote_count(request_id)

    async def vote_count(self, request_id: int) -> int:
        cursor = await self.conn.execute(
            "SELECT COUNT(*) FROM votes WHERE request_id = ?", (request_id,)
        )
        row = await cursor.fetchone()
        return row[0]

    # -- settings ----------------------------------------------------------

    async def get_setting(self, key: str) -> str | None:
        cursor = await self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.conn.commit()
