"""Shared helpers for handlers."""

from __future__ import annotations

from telegram import Update
from telegram.constants import MessageLimit
from telegram.ext import ContextTypes

from domovoy.config import Config
from domovoy.db import Database
from domovoy.render import utf16_len

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


TELEGRAM_MESSAGE_LIMIT = int(MessageLimit.MAX_TEXT_LENGTH)


def parse_request_id(args: list[str] | None) -> int | None:
    """First command arg as a request id, or None.

    isdecimal, not isdigit: isdigit also accepts characters like '⁵'
    that int() rejects with ValueError.
    """
    if not args or not args[0].isdecimal():
        return None
    return int(args[0])


def _split_at_utf16(text: str, limit: int) -> tuple[str, str]:
    """Split text so the head fits the UTF-16 budget, never inside a char."""
    units = 0
    for index, ch in enumerate(text):
        units += 2 if ord(ch) > 0xFFFF else 1
        if units > limit:
            return text[:index], text[index:]
    return text, ""


def split_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split text into Telegram-sized chunks, preferring line boundaries.

    Budgets in UTF-16 code units — Telegram's unit — so emoji-heavy text
    (astral chars count as 2) cannot produce a chunk the API rejects.
    """
    if utf16_len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    current_units = 0
    for line in text.split("\n"):
        line_units = utf16_len(line)
        while line_units > limit:  # a single pathological line
            if current:
                chunks.append(current)
                current, current_units = "", 0
            head, line = _split_at_utf16(line, limit)
            chunks.append(head)
            line_units = utf16_len(line)
        separator = 1 if current else 0
        if current_units + separator + line_units > limit:
            chunks.append(current)
            current, current_units = line, line_units
        else:
            current = f"{current}\n{line}" if current else line
            current_units += separator + line_units
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
