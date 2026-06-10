"""/help and /whoami (SPEC.md §6)."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from domovoy.handlers.common import get_config

HELP_TEXT = """\
🏠 Domovoy — HOA requests bot / бот заявок для УК

📝 Residents / Жители:
/new <text> — create a request, photo optional / создать заявку (можно с фото)
/new — guided creation / пошаговое создание
/list — open requests by votes / открытые заявки по голосам
/list done — resolved / решённые
/show <id> — request details / детали заявки
/oldest — longest-unanswered / самые давние без ответа
/whoami — your Telegram ID / ваш Telegram ID
/help — this message / эта справка

👍 Tap the button under a request to upvote (tap again to remove).
👍 Нажмите кнопку под заявкой, чтобы проголосовать (повторно — снять голос).

🔧 Coordinators / Координаторы:
/status <id> <open|progress|done|wontfix> — change status / сменить статус
/assign <id> <name> — set owner / назначить ответственного
/report [csv] — report for HOA / отчёт для УК
/digest — post the digest now / опубликовать сводку
/delete <id> — remove spam / удалить спам
"""


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT)


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    config = get_config(context)
    role = (
        "✅ You are a coordinator / Вы координатор"
        if config.is_coordinator(user.id)
        else "Resident / Житель"
    )
    await update.effective_message.reply_text(
        f"👤 {user.full_name}\n🆔 {user.id}\n{role}"
    )
