"""/report — HOA-ready summary, text or CSV (SPEC.md §5.6)."""

from __future__ import annotations

import csv
import io

from telegram import Update
from telegram.ext import ContextTypes

from domovoy.handlers.common import (
    get_db,
    reply_chunked,
    require_coordinator,
    sanitize_csv_cell,
)
from domovoy.models import Request
from domovoy.render import STATUS_LABELS, age_days, truncate, utcnow

EMPTY_REPORT = "No open requests. 🎉 / Нет открытых заявок. 🎉"

CSV_COLUMNS = ["id", "description", "votes", "age_days", "status", "owner", "created_at"]


def build_text_report(requests: list[Request]) -> str:
    now = utcnow()
    header = f"📄 Open requests for HOA / Открытые заявки для УК — {now.date().isoformat()}"
    lines = [header, ""]
    for r in requests:
        lines.append(f"#{r.id} · {truncate(r.description, 200)}")
        lines.append(
            f"   👍 {r.votes} · {age_days(r.created_at, now)} days/дн. · "
            f"{STATUS_LABELS[r.status]} · 👤 {r.owner or '—'}"
        )
    lines += ["", f"Total open / Всего открыто: {len(requests)}"]
    return "\n".join(lines)


def build_csv_report(requests: list[Request]) -> bytes:
    now = utcnow()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for r in requests:
        writer.writerow(
            [
                r.id,
                sanitize_csv_cell(r.description),
                r.votes,
                age_days(r.created_at, now),
                r.status.value,
                sanitize_csv_cell(r.owner or ""),
                r.created_at,
            ]
        )
    return buffer.getvalue().encode("utf-8")


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_coordinator(update, context):
        return
    db = get_db(context)
    chat_id = update.effective_chat.id
    requests = await db.list_open(chat_id)

    want_csv = bool(context.args) and context.args[0].lower() == "csv"
    if want_csv:
        filename = f"hoa-report-{utcnow().date().isoformat()}.csv"
        await context.bot.send_document(
            chat_id=chat_id,
            document=build_csv_report(requests),
            filename=filename,
        )
        return

    if not requests:
        await update.effective_message.reply_text(EMPTY_REPORT)
        return
    await reply_chunked(update.effective_message, build_text_report(requests))
