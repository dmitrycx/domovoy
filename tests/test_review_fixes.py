"""Regression tests for code-review and security-review findings."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domovoy.handlers.browse import list_command, show_command
from domovoy.handlers.common import sanitize_csv_cell, split_message
from domovoy.handlers.coordinator import status_command
from domovoy.handlers.report import report_command
from domovoy.handlers.requests import MAX_DESCRIPTION, guided_reply, new_command
from domovoy.handlers.voting import vote_callback
from domovoy.bot import track_group_chat
from domovoy.models import Status
from tests.conftest import (
    COORDINATOR_ID,
    GROUP_ID,
    make_photo,
    make_update,
)
from tests.test_voting import make_callback_update

OTHER_CHAT = -100999


async def seed(db, description="Broken light", group_chat_id=GROUP_ID, photo=None):
    return await db.create_request(
        group_chat_id=group_chat_id,
        author_id=1,
        author_name="Author",
        description=description,
        photo_file_id=photo,
    )


class TestGroupScoping:
    """SEC-1: requests must not be readable/votable from other chats."""

    async def test_db_get_request_scoped(self, db):
        req = await seed(db)
        assert await db.get_request(req.id, group_chat_id=GROUP_ID) is not None
        assert await db.get_request(req.id, group_chat_id=OTHER_CHAT) is None

    async def test_show_from_other_chat_not_found(self, db, context):
        req = await seed(db)
        context.args = [str(req.id)]
        update = make_update(text=f"/show {req.id}", chat_id=OTHER_CHAT)
        await show_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "not found" in text.lower()
        context.bot.send_message.assert_not_awaited()

    async def test_vote_from_other_chat_rejected(self, db, context):
        req = await seed(db)
        update = make_callback_update(f"vote:{req.id}", chat_id=OTHER_CHAT)
        await vote_callback(update, context)
        assert await db.vote_count(req.id) == 0
        update.callback_query.answer.assert_awaited_once()

    async def test_status_from_other_chat_not_found(self, db, context):
        req = await seed(db)
        context.args = [str(req.id), "done"]
        update = make_update(user_id=COORDINATOR_ID, chat_id=OTHER_CHAT)
        await status_command(update, context)
        assert (await db.get_request(req.id, group_chat_id=GROUP_ID)).status == Status.OPEN


class TestSplitMessage:
    """CR-1: outgoing messages must respect Telegram's 4096-char limit."""

    def test_short_text_single_chunk(self):
        assert split_message("hello") == ["hello"]

    def test_long_text_split_on_lines(self):
        lines = [f"line {i} " + "x" * 80 for i in range(100)]
        chunks = split_message("\n".join(lines))
        assert len(chunks) > 1
        assert all(len(c) <= 4096 for c in chunks)
        assert "\n".join(chunks).replace("\n", "") == "\n".join(lines).replace("\n", "")

    def test_giant_single_line_hard_split(self):
        chunks = split_message("x" * 10000)
        assert all(len(c) <= 4096 for c in chunks)
        assert "".join(chunks) == "x" * 10000

    async def test_list_chunked_when_huge(self, db, context):
        for i in range(120):
            await seed(db, f"req {i} " + "y" * 120)
        update = make_update(text="/list")
        await list_command(update, context)
        calls = update.effective_message.reply_text.await_args_list
        assert len(calls) >= 2
        assert all(len(c.args[0]) <= 4096 for c in calls)


class TestDescriptionCap:
    """CR-1/SEC-5: cap descriptions so cards/captions never overflow."""

    async def test_too_long_description_rejected(self, db, context):
        update = make_update(text="/new " + "x" * (MAX_DESCRIPTION + 1))
        await new_command(update, context)
        assert await db.list_open(GROUP_ID) == []
        text = update.effective_message.reply_text.await_args.args[0]
        assert str(MAX_DESCRIPTION) in text

    async def test_max_length_description_accepted(self, db, context):
        update = make_update(text="/new " + "x" * MAX_DESCRIPTION)
        await new_command(update, context)
        assert len(await db.list_open(GROUP_ID)) == 1


class TestEditedAndForeignCommands:
    """CR-2/CR-8: edited messages and other bots' commands must not act."""

    async def test_caption_for_other_bot_ignored(self, db, context):
        update = make_update(caption="/new@OtherBot fix it", photo=make_photo())
        await new_command(update, context)
        assert await db.list_open(GROUP_ID) == []

    async def test_caption_for_this_bot_accepted(self, db, context):
        update = make_update(caption="/new@DomovoyBot fix it", photo=make_photo())
        await new_command(update, context)
        assert len(await db.list_open(GROUP_ID)) == 1


class TestGuidedPhotoStash:
    """CR-4: a photo sent with bare /new must survive the guided flow."""

    async def test_initial_photo_used_when_reply_is_text_only(self, db, context):
        first = make_update(caption="/new", photo=make_photo("ph-keep"))
        await new_command(first, context)
        prompt_id = first.effective_message.reply_text.await_args  # prompt sent
        assert prompt_id is not None

        prompt = make_update(message_id=500).effective_message
        reply = make_update(text="Broken swing", user_id=42, reply_to_message=prompt)
        await guided_reply(reply, context)

        req = await db.get_request(1, group_chat_id=GROUP_ID)
        assert req.photo_file_id == "ph-keep"

    async def test_reply_photo_wins_over_stashed(self, db, context):
        first = make_update(caption="/new", photo=make_photo("ph-old"))
        await new_command(first, context)
        prompt = make_update(message_id=500).effective_message
        reply = make_update(
            caption="Broken swing",
            photo=make_photo("ph-new"),
            user_id=42,
            reply_to_message=prompt,
        )
        await guided_reply(reply, context)
        req = await db.get_request(1, group_chat_id=GROUP_ID)
        assert req.photo_file_id == "ph-new"

    async def test_new_prompt_replaces_users_previous_pending(self, db, context):
        await new_command(make_update(text="/new"), context)
        await new_command(make_update(text="/new"), context)
        pending = context.chat_data["pending_new"]
        assert len(pending) == 1  # only the latest prompt per user survives


class TestCsvSanitization:
    """SEC-3: CSV cells must not start with formula characters."""

    @pytest.mark.parametrize("payload", ["=HYPERLINK(1)", "+1", "-1", "@cmd", "\tx"])
    def test_formula_prefixes_neutralized(self, payload):
        assert not sanitize_csv_cell(payload)[0] in "=+-@\t\r"

    def test_plain_text_unchanged(self):
        assert sanitize_csv_cell("Broken light") == "Broken light"

    async def test_report_csv_neutralizes_descriptions(self, db, context):
        await seed(db, "=HYPERLINK(\"http://evil\",\"x\")")
        context.args = ["csv"]
        update = make_update(text="/report csv", user_id=COORDINATOR_ID)
        await report_command(update, context)
        body = context.bot.send_document.await_args.kwargs["document"].decode()
        assert "\n=" not in body and not body.startswith("=")
        assert "'=HYPERLINK" in body


class TestDigestTargetPinned:
    """SEC-4: the first group wins; another group cannot steal the digest."""

    async def test_second_group_does_not_overwrite(self, db, context):
        await track_group_chat(make_update(text="hi"), context)
        context.bot_data.pop("group_chat_id")  # simulate restart / cold cache
        await track_group_chat(make_update(text="hi", chat_id=OTHER_CHAT), context)
        assert await db.get_setting("group_chat_id") == str(GROUP_ID)


class TestVotesCleanup:
    """SEC-6: soft delete removes vote records (data minimization)."""

    async def test_soft_delete_purges_votes(self, db):
        req = await seed(db)
        await db.toggle_vote(req.id, 7)
        await db.soft_delete(req.id)
        assert await db.vote_count(req.id) == 0


class TestVoteAlwaysAnswered:
    """CR-7 (revised): on a DB error the handler must NOT answer the query —
    a callback query can only be answered once, and the error toast is owned
    by on_error; pre-answering here would swallow it silently."""

    async def test_no_pre_answer_on_db_error(self, db, context, monkeypatch):
        async def boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(db, "get_request", boom)
        update = make_callback_update("vote:1")
        with pytest.raises(RuntimeError):
            await vote_callback(update, context)
        update.callback_query.answer.assert_not_awaited()


class TestReportTruncation:
    """SEC-5: one long description must not break the text report."""

    async def test_text_report_truncates_descriptions(self, db, context):
        await seed(db, "z" * (MAX_DESCRIPTION - 1))
        update = make_update(text="/report", user_id=COORDINATOR_ID)
        await report_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "z" * 300 not in text
