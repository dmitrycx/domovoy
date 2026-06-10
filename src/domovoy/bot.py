"""Application wiring and entrypoint (SPEC.md §9, §10)."""

from __future__ import annotations

import logging
import os
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from domovoy.config import Config
from domovoy.db import Database
from domovoy.digest import digest_command, digest_job
from domovoy.handlers.browse import list_command, oldest_command, show_command
from domovoy.handlers.common import get_db
from domovoy.handlers.coordinator import (
    assign_command,
    delete_command,
    status_command,
)
from domovoy.handlers.info import help_command, whoami_command
from domovoy.handlers.report import report_command
from domovoy.handlers.requests import guided_reply, new_command
from domovoy.handlers.voting import vote_callback

logger = logging.getLogger(__name__)

# /new sent as a photo caption — CommandHandler only matches message text.
NEW_CAPTION_RE = r"^/new(@\w+)?(\s|$)"


def digest_schedule(config: Config) -> tuple[dtime, tuple[int, ...]]:
    """Weekly digest: Monday at DIGEST_TIME local to TZ (PTB days: 0=Sunday)."""
    hour, minute = (int(part) for part in config.digest_time.split(":"))
    return dtime(hour, minute, tzinfo=ZoneInfo(config.tz)), (1,)


async def track_group_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remember the group chat so the scheduled digest knows where to post."""
    chat = update.effective_chat
    if chat is None or chat.type not in ("group", "supergroup"):
        return
    if context.bot_data.get("group_chat_id") == chat.id:
        return
    context.bot_data["group_chat_id"] = chat.id
    await get_db(context).set_setting("group_chat_id", str(chat.id))


def build_application(config: Config) -> Application:
    db = Database(config.db_path)

    async def post_init(app: Application) -> None:
        Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)
        await db.connect()
        app.bot_data["db"] = db
        app.bot_data["config"] = config
        logger.info("database ready at %s", config.db_path)

    async def post_shutdown(app: Application) -> None:
        await db.close()

    app = (
        ApplicationBuilder()
        .token(config.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # group -1 runs before command handlers: passive group-chat tracking
    app.add_handler(TypeHandler(Update, track_group_chat), group=-1)

    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("whoami", whoami_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("show", show_command))
    app.add_handler(CommandHandler("oldest", oldest_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("assign", assign_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("digest", digest_command))

    app.add_handler(
        MessageHandler(filters.PHOTO & filters.CaptionRegex(NEW_CAPTION_RE), new_command)
    )
    app.add_handler(
        MessageHandler(
            filters.REPLY & ~filters.COMMAND & (filters.TEXT | filters.PHOTO),
            guided_reply,
        )
    )
    app.add_handler(CallbackQueryHandler(vote_callback, pattern=r"^vote:\d+$"))

    when, days = digest_schedule(config)
    app.job_queue.run_daily(digest_job, time=when, days=days, name="weekly_digest")

    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s: %(message)s", level=logging.INFO
    )
    config = Config.from_env(dict(os.environ))
    app = build_application(config)
    logger.info("starting long polling")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
