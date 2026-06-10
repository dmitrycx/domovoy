"""/list, /show, /oldest — browsing requests (SPEC.md §5.3, §5.6)."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from domovoy.handlers.common import get_db, reply_chunked
from domovoy.handlers.requests import vote_keyboard
from domovoy.render import render_card, render_list, render_list_line

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
    if not context.args or not context.args[0].isdigit():
        await message.reply_text(SHOW_USAGE)
        return
    request_id = int(context.args[0])

    db = get_db(context)
    chat_id = update.effective_chat.id
    # scoped to this chat: other chats (or DMs) can't enumerate requests
    request = await db.get_request(request_id, group_chat_id=chat_id)
    if request is None:
        await message.reply_text(NOT_FOUND.format(id=request_id))
        return

    card = render_card(request)
    keyboard = vote_keyboard(request.id, request.votes)
    if request.photo_file_id:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=request.photo_file_id,
            caption=card,
            reply_markup=keyboard,
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id, text=card, reply_markup=keyboard
        )


async def oldest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    requests = await db.oldest_open(update.effective_chat.id, limit=5)
    if not requests:
        await update.effective_message.reply_text(render_list([]))
        return
    lines = [render_list_line(r) for r in requests]
    await reply_chunked(update.effective_message, "\n".join([OLDEST_HEADER, *lines]))
