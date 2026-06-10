"""Shared helpers for handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from domovoy.config import Config
from domovoy.db import Database

NOT_COORDINATOR = (
    "⛔ Coordinators only. / Только для координаторов.\n"
    "Use /whoami to get your ID. / Используйте /whoami, чтобы узнать свой ID."
)


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.bot_data["db"]


def get_config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.bot_data["config"]


def largest_photo_id(photo: list) -> str | None:
    """Telegram sends a photo as a list of sizes; the largest is last."""
    return photo[-1].file_id if photo else None


async def require_coordinator(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """True if the user may run coordinator commands; otherwise reply and refuse."""
    if get_config(context).is_coordinator(update.effective_user.id):
        return True
    await update.effective_message.reply_text(NOT_COORDINATOR)
    return False
