"""Posting and editing request cards — the one place that owns Telegram's
length limits, so no call site can send an over-limit card."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import MessageLimit

from domovoy.models import Request
from domovoy.render import clip_utf16, render_card, vote_button_text

# Telegram counts both limits in UTF-16 code units
CAPTION_LIMIT = int(MessageLimit.CAPTION_LENGTH)
MESSAGE_LIMIT = int(MessageLimit.MAX_TEXT_LENGTH)


def vote_keyboard(request_id: int, count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(vote_button_text(count), callback_data=f"vote:{request_id}")]]
    )


async def send_card(bot, chat_id: int, request: Request):
    """Post a request card (photo or text); returns the sent Message."""
    card = render_card(request)
    keyboard = vote_keyboard(request.id, request.votes)
    if request.photo_file_id:
        return await bot.send_photo(
            chat_id=chat_id,
            photo=request.photo_file_id,
            caption=clip_utf16(card, CAPTION_LIMIT),
            reply_markup=keyboard,
        )
    return await bot.send_message(
        chat_id=chat_id, text=clip_utf16(card, MESSAGE_LIMIT), reply_markup=keyboard
    )


async def edit_card_message(
    bot,
    *,
    chat_id: int,
    msg_id: int,
    text: str,
    is_photo: bool,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit a posted card in place (caption for photo cards, text otherwise)."""
    if is_photo:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=msg_id,
            caption=clip_utf16(text, CAPTION_LIMIT),
            reply_markup=keyboard,
        )
    else:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=clip_utf16(text, MESSAGE_LIMIT),
            reply_markup=keyboard,
        )
