"""Coordinator-only commands: /status, /assign, /delete (SPEC.md §5.5, §6)
and author notifications on status change (§5.7)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from domovoy.db import Database
from domovoy.handlers.common import get_db, require_coordinator
from domovoy.handlers.requests import vote_keyboard
from domovoy.models import Request, Status
from domovoy.render import STATUS_LABELS, render_card, truncate

logger = logging.getLogger(__name__)

STATUS_USAGE = "Usage / Использование: /status <id> <open|progress|done|wontfix>"
ASSIGN_USAGE = "Usage / Использование: /assign <id> <name or @user>"
DELETE_USAGE = "Usage / Использование: /delete <id>"
NOT_FOUND = "Request #{id} not found / Заявка #{id} не найдена"
DELETED_CARD = "🗑 Request #{id} removed by a coordinator. / Заявка #{id} удалена координатором."


async def update_card(
    context: ContextTypes.DEFAULT_TYPE, request: Request
) -> None:
    """Re-render the posted card in place (text or photo caption)."""
    if request.card_chat_id is None or request.card_msg_id is None:
        return
    card = render_card(request)
    keyboard = vote_keyboard(request.id, request.votes)
    try:
        if request.photo_file_id:
            await context.bot.edit_message_caption(
                chat_id=request.card_chat_id,
                message_id=request.card_msg_id,
                caption=card,
                reply_markup=keyboard,
            )
        else:
            await context.bot.edit_message_text(
                chat_id=request.card_chat_id,
                message_id=request.card_msg_id,
                text=card,
                reply_markup=keyboard,
            )
    except TelegramError as exc:
        logger.warning("could not update card for #%s: %s", request.id, exc)


async def _notify_author(
    context: ContextTypes.DEFAULT_TYPE, request: Request, changed_by: int
) -> None:
    if request.author_id == changed_by:
        return
    text = (
        f"🔔 Your request #{request.id} «{truncate(request.description, 100)}» is now: "
        f"{STATUS_LABELS[request.status]}\n"
        f"🔔 Статус вашей заявки #{request.id} изменён."
    )
    try:
        await context.bot.send_message(chat_id=request.author_id, text=text)
    except TelegramError as exc:
        # The author may have never started a private chat with the bot.
        logger.info("could not notify author of #%s: %s", request.id, exc)


async def _fetch_request(
    db: Database, update: Update, request_id: int
) -> Request | None:
    """Chat-scoped fetch: coordinators act only on their own group's requests."""
    request = await db.get_request(request_id, group_chat_id=update.effective_chat.id)
    if request is None:
        await update.effective_message.reply_text(NOT_FOUND.format(id=request_id))
    return request


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_coordinator(update, context):
        return
    args = context.args or []
    if len(args) != 2 or not args[0].isdigit():
        await update.effective_message.reply_text(STATUS_USAGE)
        return
    try:
        status = Status(args[1].lower())
    except ValueError:
        await update.effective_message.reply_text(STATUS_USAGE)
        return

    db = get_db(context)
    request_id = int(args[0])
    if await _fetch_request(db, update, request_id) is None:
        return

    await db.set_status(request_id, status)
    request = await db.get_request(request_id)  # unscoped: re-read after update
    await update_card(context, request)
    await update.effective_message.reply_text(
        f"✅ #{request.id} → {STATUS_LABELS[status]}"
    )
    await _notify_author(context, request, changed_by=update.effective_user.id)


async def assign_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_coordinator(update, context):
        return
    args = context.args or []
    if len(args) < 2 or not args[0].isdigit():
        await update.effective_message.reply_text(ASSIGN_USAGE)
        return

    db = get_db(context)
    request_id = int(args[0])
    if await _fetch_request(db, update, request_id) is None:
        return

    owner = " ".join(args[1:])
    await db.set_owner(request_id, owner)
    request = await db.get_request(request_id)
    await update_card(context, request)
    await update.effective_message.reply_text(
        f"✅ #{request.id} → 👤 {owner}"
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_coordinator(update, context):
        return
    args = context.args or []
    if len(args) != 1 or not args[0].isdigit():
        await update.effective_message.reply_text(DELETE_USAGE)
        return

    db = get_db(context)
    request_id = int(args[0])
    request = await _fetch_request(db, update, request_id)
    if request is None:
        return

    await db.soft_delete(request_id)
    if request.card_chat_id is not None and request.card_msg_id is not None:
        notice = DELETED_CARD.format(id=request_id)
        try:
            if request.photo_file_id:
                await context.bot.edit_message_caption(
                    chat_id=request.card_chat_id,
                    message_id=request.card_msg_id,
                    caption=notice,
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=request.card_chat_id,
                    message_id=request.card_msg_id,
                    text=notice,
                )
        except TelegramError as exc:
            logger.warning("could not blank card for #%s: %s", request_id, exc)
    await update.effective_message.reply_text(
        f"🗑 #{request_id} removed / удалена"
    )
