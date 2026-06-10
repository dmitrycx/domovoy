# Implementation notes

Decisions made during implementation that refine SPEC.md. SPEC.md stays the source of
truth for *what* the bot does; this file pins down *how* where the spec left room.

## Module layout

```
src/domovoy/
  config.py    — env-var config (BOT_TOKEN, COORDINATOR_IDS, DB_PATH, DIGEST_TIME, TZ)
  models.py    — Request dataclass, Status enum (open|progress|done|wontfix)
  db.py        — Database: aiosqlite wrapper, schema per SPEC §7
  render.py    — bilingual card/list/label rendering, stale logic
  handlers/    — one module per feature area; handlers get db/config via
                 context.bot_data["db"] / ["config"]
```

## Request creation (`handlers/requests.py`)

- Commands are parsed from `message.text` **or** `message.caption` (photo single-shot
  sends the command as a caption), tolerating the `/new@BotName` form.
- Photo: Telegram delivers a list of sizes; we store the **largest** size's `file_id`.
- **Guided fallback state** lives in `context.chat_data["pending_new"]`, a dict of
  `{prompt_message_id: user_id}`. A reply creates the request only if it replies to a
  known prompt **and** comes from the user who initiated `/new` (prevents hijacking).
  State is in-memory: a bot restart drops pending prompts, which is acceptable — the
  user just sends `/new` again.
- A guided reply with no text (e.g. photo only) is re-prompted; a description is
  mandatory, the photo optional.
- Vote button `callback_data` format: `vote:<request_id>`.

## Rendering (`render.py`)

- Card per SPEC §5.4; the stale flag (`🔴 stale / нет ответа`) is appended to the
  status line when an open/in-progress request's `updated_at` is **≥ 7 days** old.
- All timestamps are stored as ISO-8601 UTC strings; rendering takes an injectable
  `now` for testability.
- List lines: `#id · 👍N · <desc ≤40 chars> · <age>d · <status emoji>[ 🔴] · <owner|—>`.

## Time & age

- `age_days` floors to whole days and never goes negative.
- "Stale" = `updated_at` at least 7 days old (`STALE_AFTER_DAYS = 7`); any status or
  owner change writes `updated_at` and so resets the clock (SPEC §5.7).
