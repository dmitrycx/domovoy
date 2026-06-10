"""Tests for coordinator-only commands (SPEC.md §5.5) and author notifications (§5.7)."""

from telegram.error import Forbidden

from domovoy.handlers.coordinator import (
    assign_command,
    delete_command,
    status_command,
)
from domovoy.models import Status
from tests.conftest import COORDINATOR_ID, GROUP_ID, make_update

AUTHOR_ID = 42


async def seed(db, description="Broken light", photo=None, author_id=AUTHOR_ID):
    req = await db.create_request(
        group_chat_id=GROUP_ID,
        author_id=author_id,
        author_name="Author",
        description=description,
        photo_file_id=photo,
    )
    await db.set_card_ref(req.id, chat_id=GROUP_ID, msg_id=700 + req.id)
    return req


class TestPermissions:
    async def test_non_coordinator_cannot_change_status(self, db, context):
        req = await seed(db)
        context.args = [str(req.id), "done"]
        update = make_update(text="/status", user_id=999)
        await status_command(update, context)

        assert (await db.get_request(req.id)).status == Status.OPEN
        text = update.effective_message.reply_text.await_args.args[0]
        assert "coordinator" in text.lower()
        assert "координатор" in text.lower()

    async def test_non_coordinator_cannot_assign(self, db, context):
        req = await seed(db)
        context.args = [str(req.id), "Ivan"]
        update = make_update(text="/assign", user_id=999)
        await assign_command(update, context)
        assert (await db.get_request(req.id)).owner is None

    async def test_non_coordinator_cannot_delete(self, db, context):
        req = await seed(db)
        context.args = [str(req.id)]
        update = make_update(text="/delete", user_id=999)
        await delete_command(update, context)
        assert await db.get_request(req.id) is not None


class TestStatus:
    async def test_coordinator_changes_status(self, db, context):
        req = await seed(db)
        context.args = [str(req.id), "progress"]
        update = make_update(text="/status", user_id=COORDINATOR_ID)
        await status_command(update, context)
        assert (await db.get_request(req.id)).status == Status.PROGRESS

    async def test_card_is_rerendered_in_place(self, db, context):
        req = await seed(db)
        context.args = [str(req.id), "done"]
        await status_command(make_update(user_id=COORDINATOR_ID), context)

        kwargs = context.bot.edit_message_text.await_args.kwargs
        assert kwargs["chat_id"] == GROUP_ID
        assert kwargs["message_id"] == 700 + req.id
        assert "Done / Сделано" in kwargs["text"]

    async def test_photo_card_uses_edit_caption(self, db, context):
        req = await seed(db, photo="ph-1")
        context.args = [str(req.id), "done"]
        await status_command(make_update(user_id=COORDINATOR_ID), context)
        context.bot.edit_message_caption.assert_awaited_once()
        context.bot.edit_message_text.assert_not_awaited()

    async def test_invalid_status_replies_usage(self, db, context):
        req = await seed(db)
        context.args = [str(req.id), "banana"]
        update = make_update(user_id=COORDINATOR_ID)
        await status_command(update, context)
        assert (await db.get_request(req.id)).status == Status.OPEN
        text = update.effective_message.reply_text.await_args.args[0]
        assert "/status" in text

    async def test_missing_args_replies_usage(self, db, context):
        context.args = []
        update = make_update(user_id=COORDINATOR_ID)
        await status_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "/status" in text

    async def test_unknown_id_replies_not_found(self, db, context):
        context.args = ["999", "done"]
        update = make_update(user_id=COORDINATOR_ID)
        await status_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "not found" in text.lower()


class TestAuthorNotification:
    async def test_author_is_notified_on_status_change(self, db, context):
        req = await seed(db)
        context.args = [str(req.id), "progress"]
        await status_command(make_update(user_id=COORDINATOR_ID), context)

        dm_calls = [
            c
            for c in context.bot.send_message.await_args_list
            if c.kwargs.get("chat_id") == AUTHOR_ID
        ]
        assert len(dm_calls) == 1
        text = dm_calls[0].kwargs["text"]
        assert f"#{req.id}" in text
        assert "In progress / В работе" in text

    async def test_author_not_notified_when_changing_own_request(self, db, context):
        req = await seed(db, author_id=COORDINATOR_ID)
        context.args = [str(req.id), "progress"]
        await status_command(make_update(user_id=COORDINATOR_ID), context)
        dm_calls = [
            c
            for c in context.bot.send_message.await_args_list
            if c.kwargs.get("chat_id") == COORDINATOR_ID
        ]
        assert dm_calls == []

    async def test_dm_failure_does_not_crash(self, db, context):
        req = await seed(db)
        context.bot.send_message.side_effect = Forbidden("bot blocked")
        context.args = [str(req.id), "done"]
        await status_command(make_update(user_id=COORDINATOR_ID), context)
        assert (await db.get_request(req.id)).status == Status.DONE


class TestAssign:
    async def test_assign_sets_owner(self, db, context):
        req = await seed(db)
        context.args = [str(req.id), "Ivan"]
        await assign_command(make_update(user_id=COORDINATOR_ID), context)
        assert (await db.get_request(req.id)).owner == "Ivan"

    async def test_assign_multiword_owner(self, db, context):
        req = await seed(db)
        context.args = [str(req.id), "Ivan", "from", "HOA"]
        await assign_command(make_update(user_id=COORDINATOR_ID), context)
        assert (await db.get_request(req.id)).owner == "Ivan from HOA"

    async def test_assign_rerenders_card(self, db, context):
        req = await seed(db)
        context.args = [str(req.id), "Ivan"]
        await assign_command(make_update(user_id=COORDINATOR_ID), context)
        kwargs = context.bot.edit_message_text.await_args.kwargs
        assert "Ivan" in kwargs["text"]

    async def test_assign_missing_args_replies_usage(self, db, context):
        context.args = ["1"]
        update = make_update(user_id=COORDINATOR_ID)
        await assign_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "/assign" in text


class TestDelete:
    async def test_delete_soft_deletes(self, db, context):
        req = await seed(db)
        context.args = [str(req.id)]
        await delete_command(make_update(user_id=COORDINATOR_ID), context)
        assert await db.get_request(req.id) is None

    async def test_delete_replaces_card(self, db, context):
        req = await seed(db)
        context.args = [str(req.id)]
        await delete_command(make_update(user_id=COORDINATOR_ID), context)
        kwargs = context.bot.edit_message_text.await_args.kwargs
        assert "removed" in kwargs["text"].lower() or "🗑" in kwargs["text"]
        assert kwargs.get("reply_markup") is None

    async def test_delete_unknown_id_replies_not_found(self, db, context):
        context.args = ["999"]
        update = make_update(user_id=COORDINATOR_ID)
        await delete_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "not found" in text.lower()
