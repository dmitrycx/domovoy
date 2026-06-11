"""/new — request creation, single-shot and guided fallback (SPEC.md §5.1)."""

from __future__ import annotations

import logging
import re

from telegram import ForceReply, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from domovoy.cards import send_card
from domovoy.handlers.common import get_db, largest_photo_id
from domovoy.render import utf16_len

logger = logging.getLogger(__name__)

# Telegram caps photo captions at 1024 UTF-16 units and the card adds chrome
# (status, author ≤64, owner ≤64 lines). 700 keeps normal cards comfortably
# inside; cards.send_card clips as the hard guarantee for pathological cases.
MAX_DESCRIPTION = 700

PROMPT_TEXT = (
    "📝 Please describe the problem (you can attach a photo) — reply to this message.\n"
    "📝 Опишите проблему (можно приложить фото) — ответьте на это сообщение."
)
TOO_LONG_TEXT = (
    f"⚠️ Description is too long (max {MAX_DESCRIPTION} characters). "
    "Please send a shorter one in reply to this message.\n"
    f"⚠️ Описание слишком длинное (максимум {MAX_DESCRIPTION} символов). "
    "Отправьте более короткое в ответ на это сообщение."
)
SEND_FAILED_TEXT = (
    "⚠️ Could not post the request card, please try again.\n"
    "⚠️ Не удалось опубликовать карточку заявки, попробуйте ещё раз."
)
GROUP_ONLY_TEXT = (
    "🏠 Requests can only be filed in the building group chat.\n"
    "🏠 Заявки можно подавать только в общем чате дома."
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


async def _send_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    photo_id: str | None,
    text: str = PROMPT_TEXT,
) -> None:
    user_id = update.effective_user.id
    prompt = await update.effective_message.reply_text(
        text, reply_markup=ForceReply(selective=True)
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
    chat = update.effective_chat
    if chat is None or chat.type not in ("group", "supergroup"):
        # a DM-created request would be invisible to the group (SPEC §5.1)
        await message.reply_text(GROUP_ONLY_TEXT)
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
    if utf16_len(description) > MAX_DESCRIPTION:
        # re-prompt so the user's shortened reply still creates the request
        # (and keeps the stashed photo) instead of being silently ignored
        await _send_prompt(update, context, photo_id, text=TOO_LONG_TEXT)
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

    try:
        sent = await send_card(context.bot, chat_id, request)
    except TelegramError as exc:
        # Don't keep an invisible request the group never saw.
        logger.warning("card post failed for #%s: %s", request.id, exc)
        await db.soft_delete(request.id)
        await update.effective_message.reply_text(SEND_FAILED_TEXT)
        return
    await db.set_card_ref(request.id, chat_id=sent.chat_id, msg_id=sent.message_id)
