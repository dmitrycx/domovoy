"""Regression tests for the second verification round (nine findings):

1. /new refused outside group chats (DM requests were invisible to the group)
2. group→supergroup migration re-homes requests and the digest target
3. split_message budgets in UTF-16 units, not Python chars
4. every card send path clips captions (shared cards.send_card)
5. a too-long description re-prompts, so the user's retry still works
6. vote_callback no longer pre-answers on errors (on_error owns the toast)
7. request-id args parsed with isdecimal (isdigit accepted '⁵', int() crashed)
8. digest age uses render.age_days (clamped at 0)
9. /oldest is a resident command (SPEC table fixed — no code change)
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from telegram import Update
from telegram.constants import MessageLimit

from domovoy.bot import build_application, on_chat_migrated, on_error
from domovoy.cards import CAPTION_LIMIT, MESSAGE_LIMIT, send_card
from domovoy.digest import build_digest
from domovoy.handlers.browse import SHOW_USAGE, show_command
from domovoy.handlers.common import parse_request_id, split_message
from domovoy.handlers.coordinator import (
    ASSIGN_USAGE,
    DELETE_USAGE,
    STATUS_USAGE,
    assign_command,
    delete_command,
    status_command,
)
from domovoy.handlers.requests import (
    GROUP_ONLY_TEXT,
    PENDING_KEY,
    TOO_LONG_TEXT,
    guided_reply,
    new_command,
)
from domovoy.handlers.voting import vote_callback
from domovoy.render import utf16_len
from tests.conftest import (
    COORDINATOR_ID,
    GROUP_ID,
    RESIDENT_ID,
    make_photo,
    make_update,
)
from tests.test_bot import make_config
from tests.test_voting import make_callback_update

NEW_GROUP_ID = -1009999


async def seed(db, description="Broken light", *, author_name="Author", photo=None):
    return await db.create_request(
        group_chat_id=GROUP_ID,
        author_id=1,
        author_name=author_name,
        description=description,
        photo_file_id=photo,
    )


# -- 1. /new outside groups -------------------------------------------------


class TestNewGroupOnly:
    async def test_dm_text_new_refused(self, db, context):
        update = make_update(text="/new Broken gate light", chat_id=555)
        update.effective_chat.type = "private"
        await new_command(update, context)
        update.effective_message.reply_text.assert_awaited_once_with(GROUP_ONLY_TEXT)
        assert await db.list_open(555) == []

    async def test_dm_photo_caption_new_refused(self, db, context):
        update = make_update(caption="/new Leak", photo=make_photo(), chat_id=555)
        update.effective_chat.type = "private"
        await new_command(update, context)
        update.effective_message.reply_text.assert_awaited_once_with(GROUP_ONLY_TEXT)
        assert await db.list_open(555) == []

    async def test_group_new_still_works(self, db, context):
        await new_command(make_update(text="/new Fix bench"), context)
        assert len(await db.list_open(GROUP_ID)) == 1


# -- 2. group→supergroup migration -------------------------------------------


class TestChatMigration:
    async def test_migrate_to_rehomes_requests_and_settings(self, db, context):
        req = await seed(db)
        await db.set_setting("group_chat_id", str(GROUP_ID))
        context.bot_data["group_chat_id"] = GROUP_ID

        update = make_update()
        update.effective_message.migrate_to_chat_id = NEW_GROUP_ID
        await on_chat_migrated(update, context)

        assert await db.get_request(req.id, group_chat_id=NEW_GROUP_ID) is not None
        assert await db.get_request(req.id, group_chat_id=GROUP_ID) is None
        assert await db.get_setting("group_chat_id") == str(NEW_GROUP_ID)
        assert context.bot_data["group_chat_id"] == NEW_GROUP_ID

    async def test_migrate_from_variant(self, db, context):
        req = await seed(db)
        await db.set_setting("group_chat_id", str(GROUP_ID))

        update = make_update(chat_id=NEW_GROUP_ID)
        update.effective_message.migrate_to_chat_id = None
        update.effective_message.migrate_from_chat_id = GROUP_ID
        await on_chat_migrated(update, context)

        assert await db.get_request(req.id, group_chat_id=NEW_GROUP_ID) is not None
        assert await db.get_setting("group_chat_id") == str(NEW_GROUP_ID)

    async def test_unrelated_pinned_group_untouched(self, db, context):
        """Migration of a second, non-pinned group must not steal the digest."""
        await db.set_setting("group_chat_id", str(GROUP_ID))
        update = make_update(chat_id=-200500)
        update.effective_message.migrate_to_chat_id = -200600
        await on_chat_migrated(update, context)
        assert await db.get_setting("group_chat_id") == str(GROUP_ID)

    def test_migration_handler_registered(self):
        app = build_application(make_config())
        handlers = [h for group in app.handlers.values() for h in group]
        assert any(getattr(h, "callback", None) is on_chat_migrated for h in handlers)


# -- 3. UTF-16 message splitting ----------------------------------------------


class TestSplitMessageUtf16:
    def test_emoji_lines_respect_utf16_budget(self):
        # 100 astral chars per line = 200 UTF-16 units; len() sees only 100
        text = "\n".join("💡" * 100 for _ in range(60))
        chunks = split_message(text)
        assert len(chunks) > 1
        assert all(utf16_len(c) <= MESSAGE_LIMIT for c in chunks)
        assert "\n".join(chunks) == text  # nothing lost at line boundaries

    def test_pathological_single_line(self):
        line = "💡" * 5000  # 10000 UTF-16 units, no newlines to split at
        chunks = split_message(line)
        assert all(utf16_len(c) <= MESSAGE_LIMIT for c in chunks)
        assert "".join(chunks) == line  # surrogate pairs never split

    def test_odd_budget_does_not_split_astral_char(self):
        chunks = split_message("💡" * 10, limit=5)  # 2 units each, budget 5
        assert all(utf16_len(c) <= 5 for c in chunks)
        assert "".join(chunks) == "💡" * 10

    def test_ascii_behavior_unchanged(self):
        assert split_message("hello") == ["hello"]
        chunks = split_message("x" * 10000)
        assert all(utf16_len(c) <= MESSAGE_LIMIT for c in chunks)
        assert "".join(chunks) == "x" * 10000


# -- 4. every card path clips captions ----------------------------------------


class TestCardClipping:
    async def test_show_clips_photo_caption(self, db, context):
        # seeded at the db layer so the rendered card is far over the
        # 1024-unit caption cap — send_card must clip regardless of source
        req = await seed(
            db, "💡" * 600, author_name="🌟" * 80, photo="ph-1"
        )
        context.args = [str(req.id)]
        update = make_update(text=f"/show {req.id}")
        await show_command(update, context)

        caption = context.bot.send_photo.await_args.kwargs["caption"]
        assert utf16_len(caption) <= CAPTION_LIMIT
        assert caption.endswith("…")

    async def test_send_card_clips_text_messages_too(self, db, context):
        req = await seed(db, "x" * 5000)  # nothing validates at the db layer
        await send_card(context.bot, GROUP_ID, req)
        text = context.bot.send_message.await_args.kwargs["text"]
        assert utf16_len(text) <= MESSAGE_LIMIT

    def test_limits_come_from_telegram_constants(self):
        assert CAPTION_LIMIT == int(MessageLimit.CAPTION_LENGTH)
        assert MESSAGE_LIMIT == int(MessageLimit.MAX_TEXT_LENGTH)


# -- 5. too-long description re-prompts ---------------------------------------


class TestTooLongReprompt:
    async def test_single_shot_too_long_arms_pending(self, db, context):
        update = make_update(text="/new " + "x" * 800)
        await new_command(update, context)

        text = update.effective_message.reply_text.await_args.args[0]
        assert text == TOO_LONG_TEXT
        # the prompt (message_id 500 in conftest) is pending — a reply works
        assert context.chat_data[PENDING_KEY] == {500: (RESIDENT_ID, None)}
        assert await db.list_open(GROUP_ID) == []

    async def test_guided_retry_after_too_long_creates_request(self, db, context):
        # photo + bare /new → prompt
        await new_command(
            make_update(caption="/new", photo=make_photo("ph-9")), context
        )
        # over-limit reply → re-prompt, photo stays stashed
        await guided_reply(
            make_update(
                text="y" * 800, reply_to_message=SimpleNamespace(message_id=500)
            ),
            context,
        )
        assert context.chat_data[PENDING_KEY] == {500: (RESIDENT_ID, "ph-9")}
        # shortened retry → request created, with the original photo
        await guided_reply(
            make_update(
                text="Broken swing", reply_to_message=SimpleNamespace(message_id=500)
            ),
            context,
        )
        requests = await db.list_open(GROUP_ID)
        assert len(requests) == 1
        assert requests[0].photo_file_id == "ph-9"
        assert context.chat_data[PENDING_KEY] == {}


# -- 6. error toast reaches the voter ------------------------------------------


class TestVoteErrorToast:
    async def test_on_error_answer_not_preempted(self, db, context, monkeypatch):
        async def boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(db, "toggle_vote", boom)
        update = make_callback_update("vote:1")
        await seed(db)
        with pytest.raises(RuntimeError) as excinfo:
            await vote_callback(update, context)
        # handler did not consume the single allowed answer...
        update.callback_query.answer.assert_not_awaited()
        # ...so on_error's toast is the first and only answer
        error_update = MagicMock(spec=Update)
        error_update.callback_query = update.callback_query
        error_update.effective_message = None
        context.error = excinfo.value
        await on_error(error_update, context)
        update.callback_query.answer.assert_awaited_once()
        assert "went wrong" in update.callback_query.answer.await_args.args[0]


# -- 7. isdecimal id parsing ----------------------------------------------------


class TestRequestIdParsing:
    def test_parse_request_id(self):
        assert parse_request_id(["5"]) == 5
        assert parse_request_id(["⁵"]) is None  # isdigit-true, int() raises
        assert parse_request_id(["abc"]) is None
        assert parse_request_id([]) is None
        assert parse_request_id(None) is None

    @pytest.mark.parametrize(
        ("handler", "args", "usage"),
        [
            (show_command, ["⁵"], SHOW_USAGE),
            (status_command, ["⁵", "done"], STATUS_USAGE),
            (assign_command, ["⁵", "Ivan"], ASSIGN_USAGE),
            (delete_command, ["⁵"], DELETE_USAGE),
        ],
    )
    async def test_superscript_id_gets_usage_not_crash(
        self, db, context, handler, args, usage
    ):
        context.args = args
        update = make_update(user_id=COORDINATOR_ID)
        await handler(update, context)
        update.effective_message.reply_text.assert_awaited_once_with(usage)


# -- 8. digest age clamped -------------------------------------------------------


class TestDigestAgeClamp:
    async def test_future_created_at_renders_zero_days(self, db):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(
            timespec="seconds"
        )
        req = await db.create_request(
            group_chat_id=GROUP_ID,
            author_id=1,
            author_name="Author",
            description="Clock skew",
            photo_file_id=None,
            now=future,
        )
        digest = build_digest([req])
        assert "0 days" in digest
        assert "-1" not in digest
