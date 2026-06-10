"""Shared fixtures: in-memory DB, config, and Telegram object mocks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from domovoy.config import Config
from domovoy.db import Database

GROUP_ID = -100123
COORDINATOR_ID = 111
RESIDENT_ID = 42


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def config():
    return Config.from_env(
        {"BOT_TOKEN": "123:abc", "COORDINATOR_IDS": str(COORDINATOR_ID)}
    )


@pytest.fixture
def context(db, config):
    ctx = MagicMock()
    ctx.bot_data = {"db": db, "config": config}
    ctx.chat_data = {}
    ctx.args = []
    ctx.bot = MagicMock()
    ctx.bot.username = "DomovoyBot"
    ctx.bot.send_message = AsyncMock(return_value=sent_message(900))
    ctx.bot.send_photo = AsyncMock(return_value=sent_message(901))
    ctx.bot.edit_message_text = AsyncMock()
    ctx.bot.edit_message_caption = AsyncMock()
    ctx.bot.edit_message_reply_markup = AsyncMock()
    return ctx


def sent_message(message_id: int, chat_id: int = GROUP_ID):
    return SimpleNamespace(message_id=message_id, chat_id=chat_id)


def make_message(
    *,
    text: str | None = None,
    caption: str | None = None,
    photo: list | None = None,
    message_id: int = 100,
    chat_id: int = GROUP_ID,
    reply_to_message=None,
):
    msg = MagicMock()
    msg.message_id = message_id
    msg.chat_id = chat_id
    msg.chat = SimpleNamespace(id=chat_id, type="supergroup")
    msg.text = text
    msg.caption = caption
    msg.photo = photo or []
    msg.reply_to_message = reply_to_message
    msg.reply_text = AsyncMock(return_value=sent_message(500, chat_id))
    msg.reply_photo = AsyncMock(return_value=sent_message(501, chat_id))
    return msg


def make_update(
    *,
    text: str | None = None,
    caption: str | None = None,
    photo: list | None = None,
    user_id: int = RESIDENT_ID,
    user_name: str = "Dmitry",
    chat_id: int = GROUP_ID,
    message_id: int = 100,
    reply_to_message=None,
):
    update = MagicMock()
    update.effective_user = SimpleNamespace(
        id=user_id, full_name=user_name, username=None
    )
    update.effective_chat = SimpleNamespace(id=chat_id, type="supergroup")
    update.effective_message = make_message(
        text=text,
        caption=caption,
        photo=photo,
        message_id=message_id,
        chat_id=chat_id,
        reply_to_message=reply_to_message,
    )
    update.callback_query = None
    return update


def make_photo(file_id: str = "photo-large"):
    """Telegram sends photos as a list of sizes, largest last."""
    return [
        SimpleNamespace(file_id="photo-small"),
        SimpleNamespace(file_id=file_id),
    ]
