"""Tests for /new — single-shot and guided creation (SPEC.md §5.1)."""

from domovoy.handlers.requests import guided_reply, new_command, parse_command_arg
from tests.conftest import GROUP_ID, make_photo, make_update


class TestParseCommandArg:
    def test_plain(self):
        assert parse_command_arg("/new Broken light") == "Broken light"

    def test_with_bot_mention(self):
        assert parse_command_arg("/new@DomovoyBot Broken light") == "Broken light"

    def test_bare_command(self):
        assert parse_command_arg("/new") == ""

    def test_strips_whitespace(self):
        assert parse_command_arg("/new   spaced   ") == "spaced"


class TestSingleShot:
    async def test_text_creates_request_and_posts_card(self, db, context):
        update = make_update(text="/new Broken light at the gate")
        await new_command(update, context)

        requests = await db.list_open(GROUP_ID)
        assert len(requests) == 1
        req = requests[0]
        assert req.description == "Broken light at the gate"
        assert req.author_id == 42
        assert req.author_name == "Dmitry"

        context.bot.send_message.assert_awaited_once()
        kwargs = context.bot.send_message.await_args.kwargs
        assert "#1" in kwargs["text"]
        assert "Broken light at the gate" in kwargs["text"]
        markup = kwargs["reply_markup"]
        assert markup.inline_keyboard[0][0].callback_data == "vote:1"

    async def test_card_ref_saved(self, db, context):
        await new_command(make_update(text="/new Fix bench"), context)
        req = await db.get_request(1)
        assert req.card_chat_id == GROUP_ID
        assert req.card_msg_id == 900

    async def test_photo_with_caption_creates_request_with_photo(self, db, context):
        update = make_update(caption="/new Broken swing", photo=make_photo("ph-123"))
        await new_command(update, context)

        req = await db.get_request(1)
        assert req.photo_file_id == "ph-123"
        context.bot.send_photo.assert_awaited_once()
        kwargs = context.bot.send_photo.await_args.kwargs
        assert kwargs["photo"] == "ph-123"
        assert "#1" in kwargs["caption"]


class TestGuidedFallback:
    async def test_bare_new_prompts_with_force_reply(self, db, context):
        update = make_update(text="/new")
        await new_command(update, context)

        assert await db.list_open(GROUP_ID) == []
        update.effective_message.reply_text.assert_awaited_once()
        kwargs = update.effective_message.reply_text.await_args.kwargs
        assert kwargs["reply_markup"].force_reply is True
        # prompt is bilingual
        text = update.effective_message.reply_text.await_args.args[0]
        assert "describe" in text.lower()
        assert "опишите" in text.lower()
        # pending registered under prompt message id, for this user
        assert context.chat_data["pending_new"][500] == 42

    async def test_reply_to_prompt_creates_request(self, db, context):
        context.chat_data["pending_new"] = {500: 42}
        prompt = make_update(message_id=500).effective_message
        update = make_update(
            text="Leaking pipe in basement", user_id=42, reply_to_message=prompt
        )
        await guided_reply(update, context)

        requests = await db.list_open(GROUP_ID)
        assert len(requests) == 1
        assert requests[0].description == "Leaking pipe in basement"
        assert context.chat_data["pending_new"] == {}

    async def test_reply_with_photo_keeps_photo(self, db, context):
        context.chat_data["pending_new"] = {500: 42}
        prompt = make_update(message_id=500).effective_message
        update = make_update(
            caption="Leaking pipe",
            photo=make_photo("ph-9"),
            user_id=42,
            reply_to_message=prompt,
        )
        await guided_reply(update, context)
        req = await db.get_request(1)
        assert req.photo_file_id == "ph-9"

    async def test_reply_from_other_user_is_ignored(self, db, context):
        context.chat_data["pending_new"] = {500: 42}
        prompt = make_update(message_id=500).effective_message
        update = make_update(text="hijack", user_id=777, reply_to_message=prompt)
        await guided_reply(update, context)
        assert await db.list_open(GROUP_ID) == []
        assert context.chat_data["pending_new"] == {500: 42}

    async def test_reply_to_unrelated_message_is_ignored(self, db, context):
        context.chat_data["pending_new"] = {}
        other = make_update(message_id=333).effective_message
        update = make_update(text="just chatting", reply_to_message=other)
        await guided_reply(update, context)
        assert await db.list_open(GROUP_ID) == []

    async def test_empty_reply_asks_again(self, db, context):
        context.chat_data["pending_new"] = {500: 42}
        prompt = make_update(message_id=500).effective_message
        update = make_update(text="   ", user_id=42, reply_to_message=prompt)
        await guided_reply(update, context)
        assert await db.list_open(GROUP_ID) == []
        # pending stays so the user can try again
        assert 500 in context.chat_data["pending_new"] or context.chat_data[
            "pending_new"
        ]
        update.effective_message.reply_text.assert_awaited_once()
