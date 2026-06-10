"""Weekly digest — build, scheduled job, and /digest command (SPEC.md §5.6, §5.7)."""

from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from domovoy.handlers.common import get_db, require_coordinator
from domovoy.models import Request
from domovoy.render import is_stale, render_list_line, truncate, utcnow

EMPTY_DIGEST = "📋 No open requests. 🎉 / Нет открытых заявок. 🎉"
STALE_HEADER = "🔴 No update in 7+ days / Без обновлений 7+ дней:"
FOOTER = "➕ New request / Новая заявка: /new <text> · All / Все: /list"


def build_digest(requests: list[Request], now: datetime | None = None) -> str:
    now = now or utcnow()
    if not requests:
        return EMPTY_DIGEST

    oldest = min(requests, key=lambda r: r.created_at)
    top = max(requests, key=lambda r: r.votes)
    oldest_age = (now - datetime.fromisoformat(oldest.created_at)).days
    oldest_desc = truncate(oldest.description, 30)
    top_desc = truncate(top.description, 30)
    owner_en = f"owner: {oldest.owner}" if oldest.owner else "no owner"
    owner_ru = f"ответственный: {oldest.owner}" if oldest.owner else "без ответственного"

    lines = [
        f"📋 {len(requests)} open · oldest «{oldest_desc}» {oldest_age} days, "
        f"{owner_en} · top voted: «{top_desc}» (👍 {top.votes})",
        f"📋 Открыто: {len(requests)} · самая старая «{oldest_desc}» — {oldest_age} дн., "
        f"{owner_ru} · топ: «{top_desc}» (👍 {top.votes})",
    ]

    stale = [r for r in requests if is_stale(r, now)]
    if stale:
        lines += ["", STALE_HEADER]
        lines += [render_list_line(r, now) for r in stale]

    lines += ["", FOOTER]
    return "\n".join(lines)


async def digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled weekly digest, posted to the group the bot serves."""
    db = get_db(context)
    raw_chat_id = await db.get_setting("group_chat_id")
    if raw_chat_id is None:
        return  # group unknown until the first command arrives from it
    chat_id = int(raw_chat_id)
    requests = await db.list_open(chat_id)
    await context.bot.send_message(chat_id=chat_id, text=build_digest(requests))


async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_coordinator(update, context):
        return
    db = get_db(context)
    requests = await db.list_open(update.effective_chat.id)
    await update.effective_message.reply_text(build_digest(requests))
