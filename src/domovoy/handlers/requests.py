"""/new — request creation, single-shot and guided fallback (SPEC.md §5.1)."""

from __future__ import annotations

import logging
import re

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from domovoy.handlers.common import get_db, largest_photo_id
from domovoy.render import render_card, vote_button_text

logger = logging.getLogger(__name__)

# Telegram photo captions cap at 1024 chars; the card adds ~150 chars of chrome,
# so this keeps every card (text or photo) well within limits.
MAX_DESCRIPTION = 800

PROMPT_TEXT = (
    "📝 Please describe the problem (you can attach a photo) — reply to this message.\n"
    "📝 Опишите проблему (можно приложить фото) — ответьте на это сообщение."
)
TOO_LONG_TEXT = (
    f"⚠️ Description is too long (max {MAX_DESCRIPTION} characters). Please shorten it.\n"
    f"⚠️ Описание слишком длинное (максимум {MAX_DESCRIPTION} символов). Сократите его."
)
SEND_FAILED_TEXT = (
    "⚠️ Could not post the request card, please try again.\n"
    "⚠️ Не удалось опубликовать карточку заявки, попробуйте ещё раз."
)

_COMMAND_RE = re.compile(r"^/\w+(?:@(?P<bot>\w+))?\s*")

# context.chat_data key: {prompt_message_id: (user_id, stashed_photo_id)}
PENDING_KEY = "pending_new"


def parse_command_arg(text: str) -> str:
    """Return the argument after `/cmd` or `/cmd@BotName`."""
    return _COMMAND_RE.sub("", text or "").strip()


def command_target_bot(text: str) -> str | None:
    """The @BotName a command is addressed to, if any."""
    match = _COMMAND_RE.match(text or "")
    return match.group("bot") if match else None


def vote_keyboard(request_id: int, count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(vote_button_text(count), callback_data=f"vote:{request_id}")]]
    )


async def _send_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, photo_id: str | None
) -> None:
    user_id = update.effective_user.id
    prompt = await update.effective_message.reply_text(
        PROMPT_TEXT, reply_markup=ForceReply(selective=True)
    )
    pending = context.chat_data.setdefault(PENDING_KEY, {})
    # one pending prompt per user — drop any earlier ones
    for msg_id in [m for m, (uid, _) in pending.items() if uid == user_id]:
        del pending[msg_id]
    pending[prompt.message_id] = (user_id, photo_id)


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if update.effective_user is None:
        return
    text = message.text or message.caption or ""
    target_bot = command_target_bot(text)
    if target_bot and target_bot.lower() != (context.bot.username or "").lower():
        return  # addressed to a different bot in the same chat

    description = parse_command_arg(text)
    photo_id = largest_photo_id(message.photo)

    if not description:
        await _send_prompt(update, context, photo_id)
        return

    await _create_request(update, context, description, photo_id)


async def guided_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A reply to the bot's guided prompt creates the request."""
    message = update.effective_message
    if update.effective_user is None:
        return
    replied_to = message.reply_to_message
    if replied_to is None:
        return
    pending = context.chat_data.get(PENDING_KEY, {})
    entry = pending.get(replied_to.message_id)
    if entry is None or entry[0] != update.effective_user.id:
        return
    stashed_photo_id = entry[1]

    description = (message.text or message.caption or "").strip()
    photo_id = largest_photo_id(message.photo) or stashed_photo_id
    if not description:
        del pending[replied_to.message_id]
        await _send_prompt(update, context, photo_id)
        return

    del pending[replied_to.message_id]
    await _create_request(update, context, description, photo_id)


async def _create_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    description: str,
    photo_id: str | None,
) -> None:
    if len(description) > MAX_DESCRIPTION:
        await update.effective_message.reply_text(TOO_LONG_TEXT)
        return

    db = get_db(context)
    user = update.effective_user
    chat_id = update.effective_chat.id

    request = await db.create_request(
        group_chat_id=chat_id,
        author_id=user.id,
        author_name=user.full_name,
        description=description,
        photo_file_id=photo_id,
    )

    card = render_card(request)
    keyboard = vote_keyboard(request.id, 0)
    try:
        if photo_id:
            sent = await context.bot.send_photo(
                chat_id=chat_id, photo=photo_id, caption=card, reply_markup=keyboard
            )
        else:
            sent = await context.bot.send_message(
                chat_id=chat_id, text=card, reply_markup=keyboard
            )
    except TelegramError as exc:
        # Don't keep an invisible request the group never saw.
        logger.warning("card post failed for #%s: %s", request.id, exc)
        await db.soft_delete(request.id)
        await update.effective_message.reply_text(SEND_FAILED_TEXT)
        return
    await db.set_card_ref(request.id, chat_id=sent.chat_id, msg_id=sent.message_id)
