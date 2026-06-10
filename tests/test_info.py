"""Tests for /help and /whoami (SPEC.md §6)."""

from domovoy.handlers.info import help_command, whoami_command
from tests.conftest import COORDINATOR_ID, make_update


class TestHelp:
    async def test_help_lists_resident_commands(self, db, context):
        update = make_update(text="/help")
        await help_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        for cmd in ("/new", "/list", "/show", "/help", "/whoami", "/oldest"):
            assert cmd in text

    async def test_help_lists_coordinator_commands(self, db, context):
        update = make_update(text="/help")
        await help_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        for cmd in ("/status", "/assign", "/report", "/digest", "/delete"):
            assert cmd in text

    async def test_help_is_bilingual(self, db, context):
        update = make_update(text="/help")
        await help_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "заявк" in text.lower()  # Russian present


class TestWhoami:
    async def test_shows_user_id(self, db, context):
        update = make_update(text="/whoami", user_id=4242, user_name="Resident Bob")
        await whoami_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "4242" in text
        assert "Resident Bob" in text

    async def test_marks_coordinator(self, db, context):
        update = make_update(text="/whoami", user_id=COORDINATOR_ID)
        await whoami_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "coordinator" in text.lower()

    async def test_resident_not_marked_coordinator(self, db, context):
        update = make_update(text="/whoami", user_id=4242)
        await whoami_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "✅" not in text
