"""Tests for /list, /list done, /show, /oldest (SPEC.md §5.3, §5.6)."""

from domovoy.handlers.browse import list_command, oldest_command, show_command
from domovoy.models import Status
from tests.conftest import GROUP_ID, make_update


async def seed(db, description="Broken light", photo=None):
    return await db.create_request(
        group_chat_id=GROUP_ID,
        author_id=1,
        author_name="Author",
        description=description,
        photo_file_id=photo,
    )


class TestList:
    async def test_list_open_sorted_by_votes(self, db, context):
        low = await seed(db, "low")
        high = await seed(db, "high")
        await db.toggle_vote(high.id, 1)
        update = make_update(text="/list")
        await list_command(update, context)

        text = update.effective_message.reply_text.await_args.args[0]
        assert text.index("#2") < text.index("#1")
        assert "high" in text

    async def test_list_empty_bilingual(self, db, context):
        update = make_update(text="/list")
        await list_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "No open requests" in text
        assert "Нет открытых заявок" in text

    async def test_list_done_shows_resolved(self, db, context):
        req = await seed(db, "fixed thing")
        await db.set_status(req.id, Status.DONE)
        context.args = ["done"]
        update = make_update(text="/list done")
        await list_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "fixed thing" in text

    async def test_list_excludes_other_groups(self, db, context):
        await db.create_request(
            group_chat_id=-555,
            author_id=1,
            author_name="X",
            description="other group req",
            photo_file_id=None,
        )
        update = make_update(text="/list")
        await list_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "other group req" not in text


class TestShow:
    async def test_show_posts_card_with_votes(self, db, context):
        req = await seed(db)
        await db.toggle_vote(req.id, 5)
        context.args = [str(req.id)]
        update = make_update(text=f"/show {req.id}")
        await show_command(update, context)

        kwargs = context.bot.send_message.await_args.kwargs
        assert "Broken light" in kwargs["text"]
        assert kwargs["reply_markup"].inline_keyboard[0][0].text == "👍 1"

    async def test_show_photo_request_sends_photo(self, db, context):
        req = await seed(db, photo="ph-1")
        context.args = [str(req.id)]
        update = make_update(text=f"/show {req.id}")
        await show_command(update, context)
        assert context.bot.send_photo.await_args.kwargs["photo"] == "ph-1"

    async def test_show_missing_id_replies_usage(self, db, context):
        context.args = []
        update = make_update(text="/show")
        await show_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "/show" in text

    async def test_show_non_numeric_replies_usage(self, db, context):
        context.args = ["abc"]
        update = make_update(text="/show abc")
        await show_command(update, context)
        update.effective_message.reply_text.assert_awaited_once()

    async def test_show_unknown_id_replies_not_found(self, db, context):
        context.args = ["999"]
        update = make_update(text="/show 999")
        await show_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "not found" in text.lower()
        assert "не найдена" in text.lower()


class TestOldest:
    async def test_oldest_lists_by_age(self, db, context):
        await seed(db, "very old request")
        await seed(db, "newer request")
        update = make_update(text="/oldest")
        await oldest_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert text.index("very old request") < text.index("newer request")

    async def test_oldest_empty_bilingual(self, db, context):
        update = make_update(text="/oldest")
        await oldest_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "No open requests" in text
