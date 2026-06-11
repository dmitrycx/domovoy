"""Inline vote toggle (SPEC.md §5.2)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from domovoy.cards import vote_keyboard
from domovoy.handlers.common import get_db

logger = logging.getLogger(__name__)

ANSWER_ADDED = "Vote counted 👍 / Голос учтён"
ANSWER_REMOVED = "Vote removed / Голос снят"
ANSWER_NOT_FOUND = "Request not found / Заявка не найдена"


async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Telegram requires the callback query to be answered or the user's client
    # spins for ~30s. Every return path below answers; on an exception the
    # answer is owned by on_error (bot.py) — answering here first would consume
    # the single allowed answer and silently swallow the error toast.
    query = update.callback_query
    try:
        request_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer(ANSWER_NOT_FOUND)
        return

    if update.effective_chat is None:
        # no chat to scope to (e.g. inline mode) — refuse rather than
        # fall back to an unscoped fetch
        await query.answer(ANSWER_NOT_FOUND)
        return

    db = get_db(context)
    # scope to the chat the button lives in — no cross-chat voting
    request = await db.get_request(
        request_id, group_chat_id=update.effective_chat.id
    )
    if request is None:
        await query.answer(ANSWER_NOT_FOUND)
        return

    voted, count = await db.toggle_vote(request_id, query.from_user.id)
    await query.answer(ANSWER_ADDED if voted else ANSWER_REMOVED)
    try:
        await query.edit_message_reply_markup(
            reply_markup=vote_keyboard(request_id, count)
        )
    except TelegramError as exc:
        # Concurrent taps can race ("message is not modified") — the vote is
        # already stored, so a failed button repaint is harmless.
        logger.debug("vote button update failed for #%s: %s", request_id, exc)
