"""Tests for /report — text and CSV (SPEC.md §5.6)."""

import csv
import io

from domovoy.handlers.report import report_command
from tests.conftest import COORDINATOR_ID, GROUP_ID, make_update


async def seed(db, description="Broken light", owner=None):
    req = await db.create_request(
        group_chat_id=GROUP_ID,
        author_id=1,
        author_name="Author",
        description=description,
        photo_file_id=None,
    )
    if owner:
        await db.set_owner(req.id, owner)
    return req


class TestReport:
    async def test_non_coordinator_rejected(self, db, context):
        update = make_update(text="/report", user_id=999)
        await report_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "coordinator" in text.lower()

    async def test_report_lists_open_requests(self, db, context):
        await seed(db, "Gate light", owner="Ivan")
        await seed(db, "Bench paint")
        update = make_update(text="/report", user_id=COORDINATOR_ID)
        await report_command(update, context)

        text = update.effective_message.reply_text.await_args.args[0]
        assert "Gate light" in text
        assert "Bench paint" in text
        assert "Ivan" in text
        assert "#1" in text and "#2" in text

    async def test_empty_report(self, db, context):
        update = make_update(text="/report", user_id=COORDINATOR_ID)
        await report_command(update, context)
        text = update.effective_message.reply_text.await_args.args[0]
        assert "No open requests" in text

    async def test_csv_report_sends_document(self, db, context):
        await seed(db, "Gate light", owner="Ivan")
        context.args = ["csv"]
        update = make_update(text="/report csv", user_id=COORDINATOR_ID)
        await report_command(update, context)

        kwargs = context.bot.send_document.await_args.kwargs
        assert kwargs["filename"].endswith(".csv")
        rows = list(csv.reader(io.StringIO(kwargs["document"].decode("utf-8"))))
        assert rows[0] == [
            "id", "description", "votes", "age_days", "status", "owner", "created_at",
        ]
        assert rows[1][1] == "Gate light"
        assert rows[1][5] == "Ivan"

    async def test_csv_handles_quotes_and_commas(self, db, context):
        await seed(db, 'Fix "the, thing"')
        context.args = ["csv"]
        update = make_update(text="/report csv", user_id=COORDINATOR_ID)
        await report_command(update, context)
        kwargs = context.bot.send_document.await_args.kwargs
        rows = list(csv.reader(io.StringIO(kwargs["document"].decode("utf-8"))))
        assert rows[1][1] == 'Fix "the, thing"'
