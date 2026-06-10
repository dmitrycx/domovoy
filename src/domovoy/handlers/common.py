"""Shared helpers for handlers."""

from __future__ import annotations

from telegram.ext import ContextTypes

from domovoy.config import Config
from domovoy.db import Database


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.bot_data["db"]


def get_config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.bot_data["config"]


def largest_photo_id(photo: list) -> str | None:
    """Telegram sends a photo as a list of sizes; the largest is last."""
    return photo[-1].file_id if photo else None
