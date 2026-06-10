"""Tests for the weekly digest (SPEC.md §5.6, §5.7)."""

from datetime import datetime, timezone

from domovoy.digest import build_digest, digest_command, digest_job
from domovoy.models import Status
from tests.conftest import COORDINATOR_ID, GROUP_ID, make_update
from tests.test_render import make_request

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


class TestBuildDigest:
    def test_empty_is_celebratory_and_bilingual(self):
        text = build_digest([], now=NOW)
        assert "No open requests" in text
        assert "Нет открытых заявок" in text

    def test_counts_and_oldest(self):
        old = make_request(
            id=1,
            description="Gate light",
            created_at="2026-03-08T10:00:00+00:00",
            votes=12,
        )
        new = make_request(
            id=2,
            description="Bench paint",
            created_at="2026-06-01T10:00:00+00:00",
            votes=1,
        )
        text = build_digest([old, new], now=NOW)
        assert "2 open" in text
        assert "Gate light" in text
        assert "94" in text
        assert "no owner" in text

    def test_oldest_shows_owner_when_assigned(self):
        req = make_request(owner="Ivan")
        text = build_digest([req], now=NOW)
        assert "Ivan" in text
        assert "no owner" not in text

    def test_top_voted_named(self):
        low = make_request(id=1, description="low votes req", votes=1)
        high = make_request(id=2, description="hot topic", votes=9)
        text = build_digest([low, high], now=NOW)
        assert "hot topic" in text
        assert "9" in text

    def test_stale_requests_called_out(self):
        stale = make_request(
            id=3, description="ignored thing", updated_at="2026-05-01T10:00:00+00:00"
        )
        text = build_digest([stale], now=NOW)
        assert "🔴" in text
        assert "#3" in text

    def test_fresh_requests_not_flagged(self):
        fresh = make_request(updated_at="2026-06-09T10:00:00+00:00")
        text = build_digest([fresh], now=NOW)
        assert "🔴" not in text


async def seed(db, **kwargs):
    return await db.create_request(
        group_chat_id=kwargs.pop("group_chat_id", GROUP_ID),
        author_id=1,
        author_name="Author",
        description=kwargs.pop("description", "Broken light"),
        photo_file_id=None,
        **kwargs,
    )


class TestDigestCommand:
    async def test_coordinator_triggers_digest(self, db, context):
        await seed(db)
        update = make_update(text="/digest", user_id=COORDINATOR_ID)
        await digest_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "1 open" in text

    async def test_non_coordinator_rejected(self, db, context):
        update = make_update(text="/digest", user_id=999)
        await digest_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "coordinator" in text.lower()


class TestDigestJob:
    async def test_posts_to_stored_group(self, db, context):
        await seed(db)
        await db.set_setting("group_chat_id", str(GROUP_ID))
        await digest_job(context)
        kwargs = context.bot.send_message.await_args.kwargs
        assert kwargs["chat_id"] == GROUP_ID
        assert "1 open" in kwargs["text"]

    async def test_skips_when_group_unknown(self, db, context):
        await digest_job(context)
        context.bot.send_message.assert_not_awaited()
