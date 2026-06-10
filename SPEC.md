# HOA Requests Bot — Specification

_Status: Draft for review · Date: 2026-06-10_

## 1. Problem

Residents ask the HOA to fix/support things (broken lights, landscaping, security,
repairs…). Today these requests live in a Telegram chat, scroll away, and often get
**no feedback for months**. There is no shared list, no priority signal, and no way to
say "this was asked 3 months ago — who is accountable?"

## 2. Goal

A **Telegram bot** added to the existing building chat that turns ad-hoc messages into a
**tracked, votable, ageable list of requests**, so residents can prioritize and the group
(including HOA reps who are present) can see status and accountability at a glance.

### Success looks like
- Any resident can file a request in **one tap/message**, with an optional photo.
- Everyone can **upvote** to push important requests up.
- Anyone can see **all open requests, their age, vote count, status, and owner**.
- A **weekly digest** auto-nudges: "5 open, oldest 94 days, no owner."
- A coordinator can produce a clean **report to hand/forward to HOA**.

### Non-goals (v1)
- Not a full property-management suite (payments, contracts, documents).
- No separate website/app (a read-only web view is a *future* nice-to-have).
- No mandatory accounts or logins — Telegram identity is enough.

## 3. Users & roles

| Role | Who | Can do |
|---|---|---|
| **Resident** | Any member of the group | Create requests, upvote, browse/list, comment via replies |
| **HOA representative** | Already in the group | Same as resident; sees everything (requests, votes, status, digest). May optionally be made a coordinator |
| **Coordinator** | Configured Telegram user IDs (you + 1–2 trusted neighbors) | Everything residents can, **plus** change status, assign owner, run reports, pin/close requests |

> HOA reps are **present in the group** and have full visibility. Day-to-day status
> updates are done by **coordinators**; HOA reps can be promoted to coordinator later
> just by adding their ID to config — no code change.

## 4. Platform & key constraint

- The bot lives in the **existing building Telegram group** (residents + HOA reps).
  ✅ Confirmed: it's a **group** where everyone can post — so members can send commands
  and tap inline vote buttons directly. (No channel-DM fallback needed.)
- Bilingual: **English + Russian** shown together in all bot messages.
- Telegram **privacy mode stays ON** (default): the bot only receives commands, replies
  to its own messages, and button taps — it does **not** read normal chat. Good for
  privacy and avoids noise.

## 5. Functional requirements

### 5.1 Submit a request — *single-shot + guided fallback*
- **Single-shot (primary):** send a photo with caption `/new <description>`, or just
  `/new <description>` as text → request created immediately.
- **Guided fallback:** send `/new` alone → bot replies (ForceReply, addressed to that
  user) asking for the description and an optional photo; their reply creates the request.
- Captured automatically: **author name, author Telegram ID, timestamp (UTC), photo
  (file_id), group chat id.**
- On creation the bot posts a **request card** (see 5.4) into the group with a vote button.

### 5.2 Upvote ("like to bump")
- Each card has an inline **👍 N** button.
- One vote per person; **tapping again removes** the vote (toggle). Dedup by Telegram user ID.
- Vote count drives default sort order in `/list`.

### 5.3 Browse
- `/list` → open requests, **sorted by votes desc**, showing per line:
  `#id · 👍N · <short description> · <age> · <status> · <owner>`.
- `/list done` → recently resolved requests.
- `/show <id>` → full detail of one request (re-posts its card).

### 5.4 Request card (the unit of display)
```
#12 · 🚧 In progress / В работе
Broken light at the main gate / Сломан фонарь у главных ворот
👤 Dmitry · 🗓 2026-03-08 (94 days ago)
👤 Owner / Ответственный: —
[ 👍 12 ]   ← inline button
```
- Photo shown above the caption when attached.
- Status & owner lines update in place when changed.

### 5.5 Status & ownership (coordinators only)
- Lifecycle: **Open → In progress → Done** (plus **Won't fix** / **Закрыто**).
- `/status <id> <open|progress|done|wontfix>` — change status (re-renders the card).
- `/assign <id> <name or @user>` — set the accountable owner.
- On change, the original author is optionally notified ("your request #12 is now In progress").

### 5.6 Accountability — digest & report
- **Weekly auto-digest** posted to the group (e.g. Monday 09:00):
  `📋 5 open · oldest "Gate light" 94 days, no owner · top voted: Gate light (12).`
- `/report` (coordinator) — a formatted, copy-paste-ready summary of all open requests
  (id, description, votes, age, status, owner) to forward/present to HOA. Optional CSV.
- `/oldest` — quick list of the longest-unanswered open requests.

### 5.7 Notifications (light)
- **Author is notified** when their request changes status (e.g. "your request #12 is
  now In progress / В работе").
- **Stale rule: every open request must get an update at least weekly.** If an open
  request has had **no status/owner change in 7+ days** (`updated_at` older than 7 days),
  it is flagged **🔴 stale / no response** in the card and called out in the weekly digest.
  Any status or owner change resets the 7-day clock.

## 6. Bot commands reference

**Residents**
| Command | Action |
|---|---|
| `/new <text>` (+photo caption) | Create a request (single-shot) |
| `/new` | Guided creation prompt |
| `/list` | Open requests by votes |
| `/list done` | Resolved requests |
| `/show <id>` | Full detail of one request |
| `/help` | How to use the bot |
| `/whoami` | Show your Telegram ID (to be added as coordinator) |

**Coordinators (also all of the above)**
| Command | Action |
|---|---|
| `/status <id> <state>` | Change status |
| `/assign <id> <owner>` | Set accountable owner |
| `/report` | Formatted report for HOA (+ optional CSV) |
| `/oldest` | Longest-unanswered open requests |
| `/digest` | Trigger the digest manually |
| `/delete <id>` | Remove spam/duplicate (soft delete) |

## 7. Data model (SQLite)

```
requests(
  id            INTEGER PK,
  group_chat_id INTEGER,        -- where it was filed / cards posted
  card_chat_id  INTEGER,        -- message location of the card
  card_msg_id   INTEGER,
  author_id     INTEGER,
  author_name   TEXT,
  description   TEXT,
  photo_file_id TEXT NULL,      -- Telegram hosts the file; we store the reference
  status        TEXT DEFAULT 'open',   -- open|progress|done|wontfix
  owner         TEXT NULL,
  created_at    TEXT,           -- ISO UTC
  updated_at    TEXT,
  deleted       INTEGER DEFAULT 0
)

votes(
  request_id INTEGER,
  user_id    INTEGER,
  PRIMARY KEY(request_id, user_id)   -- enforces one vote per person
)

settings(key TEXT PK, value TEXT)    -- group_chat_id, digest schedule, etc.
```
- **Photos cost nothing to store** — Telegram keeps the file; we keep only `file_id`.

## 8. Bilingual handling
- Every bot-authored message renders **EN + RU together** (compact, two lines).
- Status labels, buttons, digest, help — all bilingual.
- Resident-entered descriptions are stored verbatim (whatever language they wrote).

## 9. Tech stack
- **Language:** Python 3.12
- **Library:** `python-telegram-bot` v21 (async) + `[job-queue]` for the weekly digest
- **Storage:** SQLite via `aiosqlite` (single file; trivial backup)
- **Update mode:** long polling (works behind any NAT; no public URL/webhook needed)

## 10. Hosting & deployment (free)
- Candidates: **Fly.io**, **Railway**, or **Render** free tier (always-on worker), or a
  Raspberry Pi.
- SQLite file persisted on a small **mounted volume** (e.g. Fly volume at `/data`).
- Config via env vars: `BOT_TOKEN`, `COORDINATOR_IDS`, `DIGEST_TIME`, `DB_PATH`.
- Deliverables: `Dockerfile`, platform config (e.g. `fly.toml`), `.env.example`, `README`.

## 11. Privacy & moderation
- Privacy mode ON → bot never reads ordinary chat, only commands/replies/taps.
- Only author + coordinators’ actions are recorded; votes stored as user IDs (not shown
  publicly — only the count is shown).
- Coordinators can soft-delete spam/duplicates.

## 12. Non-functional
- **Free / near-free** to run.
- **Simple for non-tech users:** core actions are one message or one tap.
- **Low maintenance:** single process, single DB file, easy backup/restore.
- Scale: a building (tens–hundreds of residents, hundreds of requests) — far within SQLite + polling limits.

## 13. Out of scope (v1) / future ideas
- Read-only **web board** (same DB) for a prettier browse experience.
- Categories/tags (lighting, security, landscaping…) and filtering.
- Comment threads per request (beyond Telegram replies).
- Duplicate detection / merge.
- Multiple buildings / multiple groups from one bot.
- Photos gallery (multiple photos per request).

## 14. Resolved decisions
1. **Chat type:** ✅ a **group** — direct commands & vote taps work.
2. **Coordinators:** ✅ just the owner initially, **configurable** via `COORDINATOR_IDS`
   env var. Owner runs `/whoami` after first deploy to fetch their ID; more can be added
   anytime by editing config (no code change).
3. **Digest:** ✅ weekly, **Monday 09:00**. Timezone is a config var (`TZ` /
   `DIGEST_TIME`) — confirm your local timezone at deploy time (default to be set then).
4. **Stale rule:** ✅ open request with **no update in 7+ days = stale** (see §5.7);
   any status/owner change resets the clock.
5. **Author notifications:** ✅ notify the author on status change.
6. **Statuses:** ✅ **Open → In progress → Done → Won't fix** (all four).

> Only remaining input needed at deploy time: your **timezone** for the digest, and your
> **Telegram ID** (via `/whoami`) to seed `COORDINATOR_IDS`.
