"""/new — request creation, single-shot and guided fallback (SPEC.md §5.1)."""

from __future__ import annotations

import re

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from domovoy.handlers.common import get_db, largest_photo_id
from domovoy.render import render_card, vote_button_text

PROMPT_TEXT = (
    "📝 Please describe the problem (you can attach a photo) — reply to this message.\n"
    "📝 Опишите проблему (можно приложить фото) — ответьте на это сообщение."
)

_COMMAND_RE = re.compile(r"^/\w+(?:@\w+)?\s*")

# context.chat_data key: {prompt_message_id: user_id} awaiting a guided reply
PENDING_KEY = "pending_new"


def parse_command_arg(text: str) -> str:
    """Return the argument after `/cmd` or `/cmd@BotName`."""
    return _COMMAND_RE.sub("", text or "").strip()


def vote_keyboard(request_id: int, count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(vote_button_text(count), callback_data=f"vote:{request_id}")]]
    )


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    description = parse_command_arg(message.text or message.caption)
    photo_id = largest_photo_id(message.photo)

    if not description:
        prompt = await message.reply_text(
            PROMPT_TEXT, reply_markup=ForceReply(selective=True)
        )
        context.chat_data.setdefault(PENDING_KEY, {})[prompt.message_id] = (
            update.effective_user.id
        )
        return

    await _create_request(update, context, description, photo_id)


async def guided_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A reply to the bot's guided prompt creates the request."""
    message = update.effective_message
    replied_to = message.reply_to_message
    if replied_to is None:
        return
    pending = context.chat_data.get(PENDING_KEY, {})
    if pending.get(replied_to.message_id) != update.effective_user.id:
        return

    description = (message.text or message.caption or "").strip()
    photo_id = largest_photo_id(message.photo)
    if not description:
        prompt = await message.reply_text(
            PROMPT_TEXT, reply_markup=ForceReply(selective=True)
        )
        pending[prompt.message_id] = update.effective_user.id
        return

    del pending[replied_to.message_id]
    await _create_request(update, context, description, photo_id)


async def _create_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    description: str,
    photo_id: str | None,
) -> None:
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
    if photo_id:
        sent = await context.bot.send_photo(
            chat_id=chat_id, photo=photo_id, caption=card, reply_markup=keyboard
        )
    else:
        sent = await context.bot.send_message(
            chat_id=chat_id, text=card, reply_markup=keyboard
        )
    await db.set_card_ref(request.id, chat_id=sent.chat_id, msg_id=sent.message_id)
