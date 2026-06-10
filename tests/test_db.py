"""Tests for the SQLite data layer (SPEC.md §7)."""

import pytest

from domovoy.db import Database
from domovoy.models import Status

GROUP = -100123
AUTHOR = 42


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.connect()
    yield database
    await database.close()


async def make_request(db, description="Broken light", author_id=AUTHOR, **kwargs):
    return await db.create_request(
        group_chat_id=GROUP,
        author_id=author_id,
        author_name=kwargs.pop("author_name", "Dmitry"),
        description=description,
        photo_file_id=kwargs.pop("photo_file_id", None),
    )


class TestCreateAndGet:
    async def test_create_returns_request_with_id(self, db):
        req = await make_request(db)
        assert req.id == 1
        assert req.description == "Broken light"
        assert req.status == Status.OPEN
        assert req.author_id == AUTHOR
        assert req.owner is None
        assert req.deleted is False
        assert req.created_at == req.updated_at

    async def test_ids_increment(self, db):
        first = await make_request(db)
        second = await make_request(db, "Second")
        assert second.id == first.id + 1

    async def test_get_request(self, db):
        created = await make_request(db, photo_file_id="photo123")
        fetched = await db.get_request(created.id)
        assert fetched is not None
        assert fetched.description == "Broken light"
        assert fetched.photo_file_id == "photo123"

    async def test_get_missing_returns_none(self, db):
        assert await db.get_request(999) is None

    async def test_created_at_is_utc_iso(self, db):
        req = await make_request(db)
        # ISO-8601 UTC, parseable
        from datetime import datetime, timezone

        parsed = datetime.fromisoformat(req.created_at)
        assert parsed.tzinfo == timezone.utc


class TestCardRef:
    async def test_set_card_ref(self, db):
        req = await make_request(db)
        await db.set_card_ref(req.id, chat_id=GROUP, msg_id=777)
        fetched = await db.get_request(req.id)
        assert fetched.card_chat_id == GROUP
        assert fetched.card_msg_id == 777


class TestVotes:
    async def test_first_tap_adds_vote(self, db):
        req = await make_request(db)
        voted, count = await db.toggle_vote(req.id, user_id=7)
        assert voted is True
        assert count == 1

    async def test_second_tap_removes_vote(self, db):
        req = await make_request(db)
        await db.toggle_vote(req.id, user_id=7)
        voted, count = await db.toggle_vote(req.id, user_id=7)
        assert voted is False
        assert count == 0

    async def test_one_vote_per_user(self, db):
        req = await make_request(db)
        await db.toggle_vote(req.id, user_id=7)
        await db.toggle_vote(req.id, user_id=8)
        assert await db.vote_count(req.id) == 2


class TestStatusAndOwner:
    async def test_set_status(self, db):
        req = await make_request(db)
        await db.set_status(req.id, Status.PROGRESS)
        fetched = await db.get_request(req.id)
        assert fetched.status == Status.PROGRESS

    async def test_set_status_bumps_updated_at(self, db):
        req = await make_request(db)
        await db.set_status(req.id, Status.DONE, now="2099-01-01T00:00:00+00:00")
        fetched = await db.get_request(req.id)
        assert fetched.updated_at == "2099-01-01T00:00:00+00:00"
        assert fetched.created_at == req.created_at

    async def test_set_owner_bumps_updated_at(self, db):
        req = await make_request(db)
        await db.set_owner(req.id, "Ivan", now="2099-01-01T00:00:00+00:00")
        fetched = await db.get_request(req.id)
        assert fetched.owner == "Ivan"
        assert fetched.updated_at == "2099-01-01T00:00:00+00:00"


class TestSoftDelete:
    async def test_soft_delete_hides_from_get(self, db):
        req = await make_request(db)
        await db.soft_delete(req.id)
        assert await db.get_request(req.id) is None

    async def test_soft_delete_hides_from_lists(self, db):
        req = await make_request(db)
        await db.soft_delete(req.id)
        assert await db.list_open(GROUP) == []


class TestLists:
    async def test_list_open_sorted_by_votes_desc(self, db):
        low = await make_request(db, "low votes")
        high = await make_request(db, "high votes")
        await db.toggle_vote(high.id, 1)
        await db.toggle_vote(high.id, 2)
        await db.toggle_vote(low.id, 1)
        result = await db.list_open(GROUP)
        assert [r.id for r in result] == [high.id, low.id]
        assert result[0].votes == 2
        assert result[1].votes == 1

    async def test_list_open_excludes_done_and_wontfix(self, db):
        keep = await make_request(db, "still open")
        done = await make_request(db, "done")
        wontfix = await make_request(db, "wontfix")
        await db.set_status(done.id, Status.DONE)
        await db.set_status(wontfix.id, Status.WONTFIX)
        result = await db.list_open(GROUP)
        assert [r.id for r in result] == [keep.id]

    async def test_list_open_includes_in_progress(self, db):
        req = await make_request(db)
        await db.set_status(req.id, Status.PROGRESS)
        assert len(await db.list_open(GROUP)) == 1

    async def test_list_done(self, db):
        done = await make_request(db, "done one")
        await make_request(db, "open one")
        await db.set_status(done.id, Status.DONE)
        result = await db.list_done(GROUP)
        assert [r.id for r in result] == [done.id]

    async def test_list_open_scoped_to_group(self, db):
        await make_request(db)
        other = await db.create_request(
            group_chat_id=-999,
            author_id=1,
            author_name="X",
            description="other group",
            photo_file_id=None,
        )
        result = await db.list_open(GROUP)
        assert other.id not in [r.id for r in result]

    async def test_oldest_open_sorted_by_age(self, db):
        first = await make_request(db, "oldest")
        second = await make_request(db, "newer")
        result = await db.oldest_open(GROUP, limit=5)
        assert [r.id for r in result] == [first.id, second.id]

    async def test_oldest_open_respects_limit(self, db):
        for i in range(4):
            await make_request(db, f"req {i}")
        assert len(await db.oldest_open(GROUP, limit=2)) == 2


class TestSettings:
    async def test_get_missing_setting(self, db):
        assert await db.get_setting("nope") is None

    async def test_set_and_get_setting(self, db):
        await db.set_setting("group_chat_id", str(GROUP))
        assert await db.get_setting("group_chat_id") == str(GROUP)

    async def test_set_overwrites(self, db):
        await db.set_setting("k", "v1")
        await db.set_setting("k", "v2")
        assert await db.get_setting("k") == "v2"
