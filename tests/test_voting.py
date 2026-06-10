"""Tests for the inline vote toggle (SPEC.md §5.2)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from domovoy.handlers.voting import vote_callback
from tests.conftest import GROUP_ID, make_update


def make_callback_update(data: str, user_id: int = 42):
    update = MagicMock()
    query = MagicMock()
    query.data = data
    query.from_user = SimpleNamespace(id=user_id, full_name="Voter")
    query.answer = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    update.callback_query = query
    update.effective_user = query.from_user
    return update


async def seed_request(db, description="Broken light"):
    return await db.create_request(
        group_chat_id=GROUP_ID,
        author_id=1,
        author_name="Author",
        description=description,
        photo_file_id=None,
    )


class TestVoteCallback:
    async def test_first_tap_adds_vote_and_updates_button(self, db, context):
        req = await seed_request(db)
        update = make_callback_update(f"vote:{req.id}", user_id=7)
        await vote_callback(update, context)

        assert await db.vote_count(req.id) == 1
        update.callback_query.answer.assert_awaited_once()
        markup = update.callback_query.edit_message_reply_markup.await_args.kwargs[
            "reply_markup"
        ]
        assert markup.inline_keyboard[0][0].text == "👍 1"

    async def test_second_tap_removes_vote(self, db, context):
        req = await seed_request(db)
        await db.toggle_vote(req.id, 7)
        update = make_callback_update(f"vote:{req.id}", user_id=7)
        await vote_callback(update, context)

        assert await db.vote_count(req.id) == 0
        markup = update.callback_query.edit_message_reply_markup.await_args.kwargs[
            "reply_markup"
        ]
        assert markup.inline_keyboard[0][0].text == "👍 0"

    async def test_votes_from_different_users_accumulate(self, db, context):
        req = await seed_request(db)
        await vote_callback(make_callback_update(f"vote:{req.id}", user_id=7), context)
        await vote_callback(make_callback_update(f"vote:{req.id}", user_id=8), context)
        assert await db.vote_count(req.id) == 2

    async def test_unknown_request_answers_without_edit(self, db, context):
        update = make_callback_update("vote:999")
        await vote_callback(update, context)
        update.callback_query.answer.assert_awaited_once()
        update.callback_query.edit_message_reply_markup.assert_not_awaited()

    async def test_malformed_callback_data_is_ignored(self, db, context):
        update = make_callback_update("vote:abc")
        await vote_callback(update, context)
        update.callback_query.answer.assert_awaited_once()
        update.callback_query.edit_message_reply_markup.assert_not_awaited()

    async def test_edit_failure_does_not_crash(self, db, context):
        from telegram.error import BadRequest

        req = await seed_request(db)
        update = make_callback_update(f"vote:{req.id}")
        update.callback_query.edit_message_reply_markup.side_effect = BadRequest(
            "Message is not modified"
        )
        await vote_callback(update, context)  # must not raise
        assert await db.vote_count(req.id) == 1
