"""Coordinator-only commands: /status, /assign, /delete (SPEC.md §5.5, §6)
and author notifications on status change (§5.7)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from domovoy.cards import edit_card_message, vote_keyboard
from domovoy.db import Database
from domovoy.handlers.common import get_db, parse_request_id, require_coordinator
from domovoy.models import Request, Status
from domovoy.render import STATUS_LABELS, render_card, truncate, utf16_len

logger = logging.getLogger(__name__)

# photo captions cap at 1024 UTF-16 units; owner appears in the card chrome
MAX_OWNER = 64

STATUS_USAGE = "Usage / Использование: /status <id> <open|progress|done|wontfix>"
ASSIGN_USAGE = "Usage / Использование: /assign <id> <name or @user>"
OWNER_TOO_LONG = (
    f"⚠️ Owner name is too long (max {MAX_OWNER} characters).\n"
    f"⚠️ Имя ответственного слишком длинное (максимум {MAX_OWNER} символов)."
)
DELETE_USAGE = "Usage / Использование: /delete <id>"
NOT_FOUND = "Request #{id} not found / Заявка #{id} не найдена"
DELETED_CARD = "🗑 Request #{id} removed by a coordinator. / Заявка #{id} удалена координатором."


async def update_card(
    context: ContextTypes.DEFAULT_TYPE, request: Request
) -> None:
    """Re-render the posted card in place (text or photo caption)."""
    if request.card_chat_id is None or request.card_msg_id is None:
        return
    try:
        await edit_card_message(
            context.bot,
            chat_id=request.card_chat_id,
            msg_id=request.card_msg_id,
            text=render_card(request),
            is_photo=bool(request.photo_file_id),
            keyboard=vote_keyboard(request.id, request.votes),
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
    request_id = parse_request_id(args)
    if len(args) != 2 or request_id is None:
        await update.effective_message.reply_text(STATUS_USAGE)
        return
    try:
        status = Status(args[1].lower())
    except ValueError:
        await update.effective_message.reply_text(STATUS_USAGE)
        return

    db = get_db(context)
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
    request_id = parse_request_id(args)
    if len(args) < 2 or request_id is None:
        await update.effective_message.reply_text(ASSIGN_USAGE)
        return

    db = get_db(context)
    if await _fetch_request(db, update, request_id) is None:
        return

    owner = " ".join(args[1:])
    if utf16_len(owner) > MAX_OWNER:
        await update.effective_message.reply_text(OWNER_TOO_LONG)
        return
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
    request_id = parse_request_id(args)
    if len(args) != 1 or request_id is None:
        await update.effective_message.reply_text(DELETE_USAGE)
        return

    db = get_db(context)
    request = await _fetch_request(db, update, request_id)
    if request is None:
        return

    await db.soft_delete(request_id)
    if request.card_chat_id is not None and request.card_msg_id is not None:
        try:
            await edit_card_message(
                context.bot,
                chat_id=request.card_chat_id,
                msg_id=request.card_msg_id,
                text=DELETED_CARD.format(id=request_id),
                is_photo=bool(request.photo_file_id),
            )
        except TelegramError as exc:
            logger.warning("could not blank card for #%s: %s", request_id, exc)
    await update.effective_message.reply_text(
        f"🗑 #{request_id} removed / удалена"
    )
