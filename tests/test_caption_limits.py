"""Regression tests for verification findings: UTF-16 caption limits and
error-handler behavior on callback queries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telegram import Update

from domovoy.bot import on_error
from domovoy.handlers.coordinator import MAX_OWNER, assign_command, status_command
from domovoy.handlers.requests import MAX_DESCRIPTION, new_command
from domovoy.handlers.voting import vote_callback
from domovoy.render import clip_utf16, render_card, utf16_len
from tests.conftest import COORDINATOR_ID, GROUP_ID, make_photo, make_update
from tests.test_render import make_request
from tests.test_voting import make_callback_update

EMOJI = "😀"  # astral plane: 2 UTF-16 units


class TestUtf16Helpers:
    def test_ascii_counts_one(self):
        assert utf16_len("abc") == 3

    def test_astral_counts_two(self):
        assert utf16_len(EMOJI * 3) == 6

    def test_clip_noop_when_short(self):
        assert clip_utf16("abc", 10) == "abc"

    def test_clip_respects_utf16_budget(self):
        clipped = clip_utf16(EMOJI * 600, 1024)
        assert utf16_len(clipped) <= 1024
        assert clipped.endswith("…")

    def test_clip_never_splits_a_surrogate_pair(self):
        clipped = clip_utf16("a" + EMOJI * 600, 4)
        clipped.encode("utf-16")  # must not raise


class TestDescriptionCapIsUtf16:
    async def test_emoji_description_over_budget_rejected(self, db, context):
        # codepoint count is under the cap, UTF-16 count is over
        update = make_update(text="/new " + EMOJI * (MAX_DESCRIPTION // 2 + 10))
        await new_command(update, context)
        assert await db.list_open(GROUP_ID) == []


class TestCaptionNeverOverflows:
    async def test_photo_caption_within_1024_with_hostile_inputs(self, db, context):
        long_name = "Имя" * 43  # 129 chars — Telegram allows up to 64+64
        update = make_update(
            caption="/new " + "x" * MAX_DESCRIPTION,
            photo=make_photo(),
            user_name=long_name,
        )
        await new_command(update, context)
        caption = context.bot.send_photo.await_args.kwargs["caption"]
        assert utf16_len(caption) <= 1024

    async def test_card_update_caption_within_1024(self, db, context):
        req = await db.create_request(
            group_chat_id=GROUP_ID,
            author_id=1,
            author_name="N" * 129,
            description=EMOJI * 350,
            photo_file_id="ph-1",
        )
        await db.set_card_ref(req.id, chat_id=GROUP_ID, msg_id=701)
        context.args = [str(req.id), "progress"]
        await status_command(make_update(user_id=COORDINATOR_ID), context)
        caption = context.bot.edit_message_caption.await_args.kwargs["caption"]
        assert utf16_len(caption) <= 1024

    def test_render_card_truncates_author_and_owner(self):
        req = make_request(author_name="A" * 200, owner="O" * 200)
        card = render_card(req)
        assert "A" * 100 not in card
        assert "O" * 100 not in card


class TestOwnerCap:
    async def test_assign_rejects_overlong_owner(self, db, context):
        req = await db.create_request(
            group_chat_id=GROUP_ID,
            author_id=1,
            author_name="A",
            description="d",
            photo_file_id=None,
        )
        context.args = [str(req.id), "x" * (MAX_OWNER + 1)]
        update = make_update(user_id=COORDINATOR_ID)
        await assign_command(update, context)
        assert (await db.get_request(req.id)).owner is None


class TestVoteCallbackEdgeCases:
    async def test_no_effective_chat_refuses_instead_of_unscoped(self, db, context):
        req = await db.create_request(
            group_chat_id=GROUP_ID,
            author_id=1,
            author_name="A",
            description="d",
            photo_file_id=None,
        )
        update = make_callback_update(f"vote:{req.id}")
        update.effective_chat = None
        await vote_callback(update, context)
        assert await db.vote_count(req.id) == 0
        update.callback_query.answer.assert_awaited_once()


class TestErrorHandler:
    async def test_callback_error_answers_privately(self, context):
        update = MagicMock(spec=Update)
        update.callback_query = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.effective_message = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        context.error = RuntimeError("boom")

        await on_error(update, context)

        update.callback_query.answer.assert_awaited_once()
        update.effective_message.reply_text.assert_not_awaited()

    async def test_message_error_replies(self, context):
        update = MagicMock(spec=Update)
        update.callback_query = None
        update.effective_message = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        context.error = RuntimeError("boom")

        await on_error(update, context)
        update.effective_message.reply_text.assert_awaited_once()
