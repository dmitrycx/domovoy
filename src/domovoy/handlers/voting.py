"""Inline vote toggle (SPEC.md §5.2)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from domovoy.handlers.common import get_db
from domovoy.handlers.requests import vote_keyboard

logger = logging.getLogger(__name__)

ANSWER_ADDED = "Vote counted 👍 / Голос учтён"
ANSWER_REMOVED = "Vote removed / Голос снят"
ANSWER_NOT_FOUND = "Request not found / Заявка не найдена"


async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    answered = False
    try:
        try:
            request_id = int(query.data.split(":", 1)[1])
        except (IndexError, ValueError):
            await query.answer(ANSWER_NOT_FOUND)
            answered = True
            return

        db = get_db(context)
        # scope to the chat the button lives in — no cross-chat voting
        chat_id = update.effective_chat.id if update.effective_chat else None
        request = await db.get_request(request_id, group_chat_id=chat_id)
        if request is None:
            await query.answer(ANSWER_NOT_FOUND)
            answered = True
            return

        voted, count = await db.toggle_vote(request_id, query.from_user.id)
        await query.answer(ANSWER_ADDED if voted else ANSWER_REMOVED)
        answered = True
        try:
            await query.edit_message_reply_markup(
                reply_markup=vote_keyboard(request_id, count)
            )
        except TelegramError as exc:
            # Concurrent taps can race ("message is not modified") — the vote is
            # already stored, so a failed button repaint is harmless.
            logger.debug("vote button update failed for #%s: %s", request_id, exc)
    finally:
        if not answered:
            # Telegram requires an answer or the user's client spins for ~30s.
            try:
                await query.answer()
            except TelegramError:
                pass
