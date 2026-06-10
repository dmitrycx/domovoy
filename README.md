# 🏠 Domovoy — HOA Requests Bot

> _Домовой_ — the household guardian spirit of Slavic folklore. This one keeps an eye on
> your building's open requests so none of them get forgotten.

A simple, free **Telegram bot** for housing complexes. Residents file maintenance/support
requests (with a photo), neighbors **upvote** to prioritize, and everyone — including HOA
reps in the chat — can see **status, age, and who's accountable**. No more requests that
scroll away and go unanswered for months.

Bilingual 🇬🇧 EN / 🇷🇺 RU.

## Why

In most building chats, requests to the HOA get buried and receive no feedback for months.
Domovoy turns those messages into a tracked, votable, ageable list — and nudges weekly:
_"5 open · oldest 94 days, no owner."_

## Features

- 📝 File a request in one message: `/new <description>` (+ optional photo)
- 👍 One-tap upvoting (one vote per person) to bump priority
- 📋 `/list` — open requests sorted by votes, showing age & status
- 🔧 Coordinators set **status** (Open → In progress → Done → Won't fix) and an **owner**
- 🔴 **Stale flag** — any open request with no update in 7+ days is called out
- 🗓 Weekly digest + `/report` to hand the HOA a clean summary
- 🔔 Authors notified when their request's status changes

## Status

🚧 **Spec phase.** Design is finalized — see **[SPEC.md](./SPEC.md)**. Implementation next.

## Tech (planned)

Python · [`python-telegram-bot`](https://docs.python-telegram-bot.org/) v21 · SQLite ·
long-polling · free cloud hosting (Fly.io / Railway / Render).

## License

MIT (planned).
