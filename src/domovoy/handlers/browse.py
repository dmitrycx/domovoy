"""/list, /show, /oldest — browsing requests (SPEC.md §5.3, §5.6)."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from domovoy.cards import send_card
from domovoy.handlers.common import get_db, parse_request_id, reply_chunked
from domovoy.render import render_list, render_list_line

SHOW_USAGE = "Usage / Использование: /show <id>"
NOT_FOUND = "Request #{id} not found / Заявка #{id} не найдена"
OLDEST_HEADER = "⏳ Longest-unanswered / Дольше всего без ответа:"


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    chat_id = update.effective_chat.id
    done = bool(context.args) and context.args[0].lower() == "done"
    if done:
        requests = await db.list_done(chat_id)
    else:
        requests = await db.list_open(chat_id)
    await reply_chunked(update.effective_message, render_list(requests, done=done))


async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    request_id = parse_request_id(context.args)
    if request_id is None:
        await message.reply_text(SHOW_USAGE)
        return

    db = get_db(context)
    chat_id = update.effective_chat.id
    # scoped to this chat: other chats (or DMs) can't enumerate requests
    request = await db.get_request(request_id, group_chat_id=chat_id)
    if request is None:
        await message.reply_text(NOT_FOUND.format(id=request_id))
        return

    await send_card(context.bot, chat_id, request)


async def oldest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    requests = await db.oldest_open(update.effective_chat.id, limit=5)
    if not requests:
        await update.effective_message.reply_text(render_list([]))
        return
    lines = [render_list_line(r) for r in requests]
    await reply_chunked(update.effective_message, "\n".join([OLDEST_HEADER, *lines]))
