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

## Voting (`handlers/voting.py`)

- The callback query is **always answered** (Telegram requires it within seconds).
- A failed button repaint (e.g. "message is not modified" race from concurrent taps)
  is logged and ignored — the vote itself is already persisted.

## Coordinator actions (`handlers/coordinator.py`)

- Permission = `user_id ∈ COORDINATOR_IDS` (config), checked per command; everyone
  else gets a bilingual rejection pointing at `/whoami`.
- Card re-render edits the original message in place: `edit_message_caption` for
  photo cards, `edit_message_text` otherwise; failures are logged, never fatal.
- Author notification is a **DM** (`send_message` to `author_id`). It is skipped when
  the coordinator changes their own request, and silently tolerated when the author
  never opened a private chat with the bot (Telegram forbids unsolicited DMs).
- `/delete` soft-deletes in the DB and blanks the card to a removal notice
  (button gone), keeping the audit row.

## Digest & report (`digest.py`, `handlers/report.py`)

- The scheduled digest needs a destination: the bot **passively records the group
  chat id** (a `TypeHandler` in group −1 stores it in `settings.group_chat_id` on the
  first group update, cached in `bot_data` after that). Until any group activity
  happens, the scheduled digest silently skips.
- Schedule: PTB `run_daily` with `days=(1,)` — PTB numbers days **0=Sunday**, so 1 is
  Monday — at `DIGEST_TIME` local to `TZ`.
- `/report` posts a text report; `/report csv` sends a CSV document
  (`id,description,votes,age_days,status,owner,created_at`).

## Wiring (`bot.py`)

- `/new` as a **photo caption** doesn't trigger `CommandHandler` (it only matches
  message text), so a `MessageHandler(PHOTO & CaptionRegex(^/new))` is registered too.
- Guided replies: `MessageHandler(REPLY & ~COMMAND & (TEXT | PHOTO))` — the handler
  itself filters down to replies to known prompts.
- DB connect/close hang off `post_init`/`post_shutdown`; handlers reach the DB and
  config through `bot_data`. The DB directory is created on startup.
- Long polling with `allowed_updates=Update.ALL_TYPES`.

## Hardening (from code & security review)

- **Chat scoping:** `/show`, vote callbacks, and all coordinator commands fetch
  requests scoped to the chat they were invoked from (`get_request(id, group_chat_id)`),
  so request data can't be enumerated from DMs or another group.
- **Telegram limits:** descriptions are capped at 800 chars at intake (photo captions
  cap at 1024 incl. ~150 chars of card chrome); `/list`, `/report`, `/digest` output is
  chunked at 4096; the digest lists at most 10 stale lines (+ "and N more"); the text
  report truncates descriptions at 200 chars (CSV keeps them full).
- **Edited messages don't act:** all command/message handlers filter on
  `UpdateType.MESSAGE`, so editing `/new ...` doesn't file a duplicate.
- **Digest target pinned:** first group wins; adding the bot to another group logs a
  warning instead of re-targeting the digest. Migrate by editing the
  `group_chat_id` settings row.
- **CSV cells** starting with `=`, `+`, `-`, `@`, tab, or CR get an apostrophe prefix
  (spreadsheet formula-injection guard).
- **Token hygiene:** `httpx`/`httpcore` loggers are capped at WARNING — at INFO httpx
  logs every Bot API URL, which contains the token.
- **Failed card posts roll back** the just-created request and tell the user, instead
  of keeping an invisible row.
- **Guided flow:** a photo sent with a bare `/new` caption is stashed in the pending
  entry and attached when the text-only reply arrives; one pending prompt per user.
- **Votes are purged** when a request is soft-deleted (data minimization).
- **Deviation from SPEC §6:** `/oldest` is intentionally open to all residents (the
  spec table lists it under coordinators); there's nothing sensitive in it and it
  supports the accountability goal.

## Time & age

- `age_days` floors to whole days and never goes negative.
- "Stale" = `updated_at` at least 7 days old (`STALE_AFTER_DAYS = 7`); any status or
  owner change writes `updated_at` and so resets the clock (SPEC §5.7).
