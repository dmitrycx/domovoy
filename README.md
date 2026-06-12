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

✅ **Implemented.** Design in **[SPEC.md](./SPEC.md)**, implementation decisions in
[docs/IMPLEMENTATION.md](./docs/IMPLEMENTATION.md).

## Quick start (local)

Requires [uv](https://docs.astral.sh/uv/) (it fetches Python 3.12 automatically).

```bash
uv sync                      # install deps into .venv
cp .env.example .env         # fill in BOT_TOKEN (from @BotFather)
set -a && source .env && set +a
uv run python -m domovoy     # starts long polling
```

Then add the bot to your building group, send `/whoami`, and put your ID into
`COORDINATOR_IDS` to unlock `/status`, `/assign`, `/report`, `/digest`, `/delete`.

> **BotFather settings:** keep *Group Privacy* **ON** (the bot must not read ordinary
> chat) and, once the bot is in your group, consider disabling *Allow Groups* so
> strangers can't add it elsewhere. The weekly digest is pinned to the first group
> the bot sees. Coordinators posting as *anonymous admins* won't be recognized —
> Telegram hides their user ID.

Run the tests:

```bash
uv run pytest
```

## Deploy (Fly.io free tier)

The bot is a long-polling worker — no public URL needed. SQLite lives on a 1 GB volume.

One-time setup:

```bash
fly launch --no-deploy                 # uses the provided fly.toml + Dockerfile
fly volumes create domovoy_data --size 1
fly secrets set BOT_TOKEN=... COORDINATOR_IDS=...
fly deploy                             # first deploy, by hand
```

Config is all env vars: `BOT_TOKEN`, `COORDINATOR_IDS`, `DB_PATH`, `DIGEST_TIME`, `TZ`
— see [.env.example](./.env.example).

### CI/CD (GitHub Actions)

[.github/workflows/ci.yml](./.github/workflows/ci.yml) runs tests and a Docker build
on every push and pull request; pushes to `main` then deploy to Fly automatically.
To enable the deploy step after the one-time setup above:

```bash
fly tokens create deploy            # scoped to this app only
gh secret set FLY_API_TOKEN         # paste the token (or use repo Settings → Secrets)
```

Until `FLY_API_TOKEN` is set, the deploy job skips with a warning instead of failing.
Deploys are serialized (`concurrency: fly-deploy`) — a single machine with SQLite
must never deploy concurrently.

## Tech

Python 3.12 · [`python-telegram-bot`](https://docs.python-telegram-bot.org/) v21
(async, job-queue) · SQLite via `aiosqlite` · long polling · 193 tests (pytest) ·
GitHub Actions CI/CD.

## License

MIT (planned).
