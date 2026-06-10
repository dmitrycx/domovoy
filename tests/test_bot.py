"""Tests for application wiring (handlers, digest schedule, group tracking)."""

from datetime import time as dtime
from zoneinfo import ZoneInfo

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from domovoy.bot import build_application, digest_schedule, track_group_chat
from domovoy.config import Config
from tests.conftest import GROUP_ID, make_update

EXPECTED_COMMANDS = {
    "start", "help", "whoami", "new", "list", "show", "oldest",
    "status", "assign", "delete", "report", "digest",
}


def make_config(**overrides):
    env = {"BOT_TOKEN": "123:abc", "COORDINATOR_IDS": "111"}
    env.update(overrides)
    return Config.from_env(env)


class TestDigestSchedule:
    def test_monday_at_configured_local_time(self):
        when, days = digest_schedule(make_config(DIGEST_TIME="09:00", TZ="Europe/Belgrade"))
        assert when == dtime(9, 0, tzinfo=ZoneInfo("Europe/Belgrade"))
        assert days == (1,)  # PTB: 0=Sunday, 1=Monday


class TestBuildApplication:
    def test_all_commands_registered(self):
        app = build_application(make_config())
        registered = set()
        for group in app.handlers.values():
            for handler in group:
                if isinstance(handler, CommandHandler):
                    registered |= set(handler.commands)
        assert EXPECTED_COMMANDS <= registered

    def test_vote_callback_and_message_handlers_registered(self):
        app = build_application(make_config())
        handlers = [h for group in app.handlers.values() for h in group]
        assert any(isinstance(h, CallbackQueryHandler) for h in handlers)
        assert any(isinstance(h, MessageHandler) for h in handlers)

    def test_weekly_digest_job_scheduled(self):
        app = build_application(make_config())
        names = [job.name for job in app.job_queue.jobs()]
        assert "weekly_digest" in names


class TestGroupTracking:
    async def test_group_chat_id_persisted(self, db, context):
        update = make_update(text="anything")
        await track_group_chat(update, context)
        assert await db.get_setting("group_chat_id") == str(GROUP_ID)

    async def test_private_chat_not_tracked(self, db, context):
        update = make_update(text="hi", chat_id=42)
        update.effective_chat.type = "private"
        await track_group_chat(update, context)
        assert await db.get_setting("group_chat_id") is None

    async def test_cached_after_first_write(self, db, context):
        update = make_update(text="anything")
        await track_group_chat(update, context)
        await db.set_setting("group_chat_id", "tampered")
        await track_group_chat(update, context)  # cached — no rewrite
        assert await db.get_setting("group_chat_id") == "tampered"
