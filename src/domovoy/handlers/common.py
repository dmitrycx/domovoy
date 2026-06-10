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


TELEGRAM_MESSAGE_LIMIT = 4096


def split_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split text into Telegram-sized chunks, preferring line boundaries."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:  # a single pathological line
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def reply_chunked(message, text: str) -> None:
    for chunk in split_message(text):
        await message.reply_text(chunk)


def sanitize_csv_cell(value: str) -> str:
    """Neutralize spreadsheet formula injection (=, +, -, @, tab, CR prefixes)."""
    if value and value[0] in "=+-@\t\r":
        return "'" + value
    return value
