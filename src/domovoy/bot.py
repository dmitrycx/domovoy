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
    """Remember the group chat so the scheduled digest knows where to post.

    First group wins: once set, the digest target is never overwritten, so adding
    the bot to a second group cannot hijack the weekly digest (change the
    `group_chat_id` row in the settings table to migrate deliberately).
    """
    chat = update.effective_chat
    if chat is None or chat.type not in ("group", "supergroup"):
        return
    if context.bot_data.get("group_chat_id") is not None:
        return
    db = get_db(context)
    stored = await db.get_setting("group_chat_id")
    if stored is None:
        await db.set_setting("group_chat_id", str(chat.id))
        stored = str(chat.id)
        logger.info("digest target group set to %s", chat.id)
    elif stored != str(chat.id):
        logger.warning(
            "update from group %s ignored as digest target; pinned to %s",
            chat.id,
            stored,
        )
    context.bot_data["group_chat_id"] = int(stored)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("unhandled error processing update", exc_info=context.error)
    if not isinstance(update, Update):
        return
    error_text = (
        "⚠️ Something went wrong, please try again. / Что-то пошло не так, попробуйте ещё раз."
    )
    try:
        if update.callback_query is not None:
            # answer only the tapping user — a reply would be a public group message
            await update.callback_query.answer(error_text[:200])
        elif update.effective_message:
            await update.effective_message.reply_text(error_text)
    except Exception:  # noqa: BLE001 — never raise from the error handler
        pass


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

    # only fresh messages — otherwise editing a command re-executes it
    # (e.g. fixing a typo in `/new ...` would file a duplicate request)
    fresh = filters.UpdateType.MESSAGE

    commands = {
        "start": help_command,
        "help": help_command,
        "whoami": whoami_command,
        "new": new_command,
        "list": list_command,
        "show": show_command,
        "oldest": oldest_command,
        "status": status_command,
        "assign": assign_command,
        "delete": delete_command,
        "report": report_command,
        "digest": digest_command,
    }
    for name, callback in commands.items():
        app.add_handler(CommandHandler(name, callback, filters=fresh))

    app.add_handler(
        MessageHandler(
            fresh & filters.PHOTO & filters.CaptionRegex(NEW_CAPTION_RE), new_command
        )
    )
    app.add_handler(
        MessageHandler(
            fresh & filters.REPLY & ~filters.COMMAND & (filters.TEXT | filters.PHOTO),
            guided_reply,
        )
    )
    app.add_handler(CallbackQueryHandler(vote_callback, pattern=r"^vote:\d+$"))
    app.add_error_handler(on_error)

    when, days = digest_schedule(config)
    app.job_queue.run_daily(digest_job, time=when, days=days, name="weekly_digest")

    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s: %(message)s", level=logging.INFO
    )
    # httpx logs every request URL at INFO — for the Bot API that URL contains
    # the bot token, which must never reach the logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    config = Config.from_env(dict(os.environ))
    app = build_application(config)
    logger.info("starting long polling")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
