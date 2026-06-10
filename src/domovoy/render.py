"""Bilingual (EN+RU) rendering of cards, lists, and labels (SPEC.md §5.4, §8)."""

from __future__ import annotations

from datetime import datetime, timezone

from domovoy.models import Request, Status

STALE_AFTER_DAYS = 7

STATUS_LABELS: dict[Status, str] = {
    Status.OPEN: "🟢 Open / Открыта",
    Status.PROGRESS: "🚧 In progress / В работе",
    Status.DONE: "✅ Done / Сделано",
    Status.WONTFIX: "⛔ Won't fix / Закрыто",
}

STATUS_EMOJI: dict[Status, str] = {
    Status.OPEN: "🟢",
    Status.PROGRESS: "🚧",
    Status.DONE: "✅",
    Status.WONTFIX: "⛔",
}

STALE_FLAG = "🔴 stale / нет ответа"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def age_days(created_at: str, now: datetime) -> int:
    created = datetime.fromisoformat(created_at)
    return max(0, (now - created).days)


def is_stale(request: Request, now: datetime) -> bool:
    """Open/in-progress request with no update for STALE_AFTER_DAYS+ days (§5.7)."""
    if request.status not in (Status.OPEN, Status.PROGRESS):
        return False
    return age_days(request.updated_at, now) >= STALE_AFTER_DAYS


def truncate(text: str, limit: int = 40) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def vote_button_text(count: int) -> str:
    return f"👍 {count}"


def render_card(request: Request, now: datetime | None = None) -> str:
    now = now or utcnow()
    days = age_days(request.created_at, now)
    created_date = request.created_at[:10]
    status_line = f"#{request.id} · {STATUS_LABELS[request.status]}"
    if is_stale(request, now):
        status_line += f" · {STALE_FLAG}"
    return (
        f"{status_line}\n"
        f"{request.description}\n"
        f"👤 {request.author_name} · 🗓 {created_date} ({days} days ago / дн. назад)\n"
        f"👤 Owner / Ответственный: {request.owner or '—'}"
    )


def render_list_line(request: Request, now: datetime | None = None) -> str:
    now = now or utcnow()
    days = age_days(request.created_at, now)
    stale = " 🔴" if is_stale(request, now) else ""
    return (
        f"#{request.id} · 👍{request.votes} · {truncate(request.description)} · "
        f"{days}d · {STATUS_EMOJI[request.status]}{stale} · {request.owner or '—'}"
    )


def render_list(
    requests: list[Request], now: datetime | None = None, done: bool = False
) -> str:
    now = now or utcnow()
    if not requests:
        if done:
            return "No resolved requests yet. / Нет решённых заявок."
        return "No open requests. 🎉 / Нет открытых заявок. 🎉"
    if done:
        header = "✅ Recently resolved / Недавно решённые:"
    else:
        header = "📋 Open requests by votes / Открытые заявки по голосам:"
    lines = [render_list_line(r, now) for r in requests]
    return "\n".join([header, *lines])
