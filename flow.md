# `flow.md` (current codebase behavior)

This is the single source-of-truth documentation for what is implemented right now (no “future design”). It is derived by reading the code under `bot/` and `database/`.

Stack: `aiogram` bot + optional `FastAPI` webhook server + PostgreSQL (`postgresql+asyncpg`) via async SQLAlchemy (configured by `DATABASE_URL`) + Mercle SDK calls over `httpx`.

## Runtime / entrypoints

### Polling mode
File: `bot/main.py`
- Loads config via `Config.from_env()`.
- Initializes `TelegramBot` (DB, services, routers).
- Runs `Dispatcher.start_polling(...)`.

### Webhook server mode
File: `webhook_server.py`
- FastAPI lifespan:
  - Creates/initializes `TelegramBot` and calls `start()` (this also starts the periodic cleanup task).
  - Sets a Telegram webhook and forwards incoming updates into `Dispatcher.feed_update(...)`.
  - On shutdown, deletes the webhook and stops the bot.
- HTTP endpoints:
  - `POST <WEBHOOK_PATH>`: Telegram webhook updates.
  - `GET /`: basic info + links to endpoints.
  - `GET /verify`: serves `static/verify.html` (deep-link helper for Mercle).
  - `GET /health`: always returns a minimal liveness payload; includes DB status only when `ADMIN_API_TOKEN` is set + provided.
  - `GET /status`: returns detailed metrics only when `ADMIN_API_TOKEN` is set + provided.
- Admin token transport:
  - `Authorization: Bearer <token>`, or `X-Admin-Token: <token>`, or `?token=<token>`

### Bot wiring (shared)
File: `bot/main.py`
- Creates: `Bot`, `Dispatcher`, DI container (`ServiceContainer`)
- Includes routers (message handlers are last so they don’t intercept commands):
  - `bot/handlers/commands.py` (DM home/help, deep links, DM settings)
  - `bot/handlers/admin_commands.py` (moderation + roles + diagnostics)
  - `bot/handlers/content_commands.py` (notes/filters/rules/welcome)
  - `bot/handlers/member_events.py` (join/post-join verification)
  - `bot/handlers/member_events.py` (setup card when bot is added)
  - `bot/handlers/member_events.py` (leave/goodbye)
  - `bot/handlers/join_requests.py` (join-gate verification via join requests)
  - `bot/handlers/rbac_help.py` (`/mycommands`)
  - `bot/handlers/message_handlers.py` (locks/antiflood/filters/notes triggers)
- Sets Telegram command menus (scoped for private / groups / group-admins) via `set_my_commands(...)`.

### Logging (what you will and won’t see)
- `bot/main.py` logs to stdout and `bot.log`.
- `webhook_server.py` logs a safe per-update summary:
  - commands are logged as `cmd=/...`
  - private non-command messages log only `text_len=...`
  - raw user message text is never logged; non-command group messages are not logged

### Periodic cleanup
File: `bot/main.py`
- Runs every ~60s (started by `TelegramBot.start()`, so it runs in both polling + webhook mode):
  - Marks expired `verification_sessions` as `expired` (does not delete rows).
  - Finds expired `pending_join_verifications` and:
    - `kind="join_request"`: best-effort declines the join request, marks pending `timed_out`.
    - `kind="post_join"`: kicks (ban+unban) if `groups.kick_unverified`, otherwise keeps user muted; marks pending `timed_out` and edits/deletes the group prompt best-effort.

## Database (tables + what they mean)
File: `database/models.py` (migrated via Alembic)

Runtime:
- `DATABASE_URL` is required (no SQLite fallback).
- Schema is created via Alembic migrations (no runtime migrations); deploy runs `alembic upgrade head`.
- On startup, the bot requires `alembic_version` to exist (`db.require_schema()`), and fails fast if the schema wasn’t migrated.

### Global verification
- `users` (`User`)
  - `telegram_id` (PK), `mercle_user_id` (unique), username/names, `verified_at`
  - Once present, the user is treated as globally “verified” across all groups.

### Mercle verification sessions (polling state)
- `verification_sessions` (`VerificationSession`)
  - Tracks Mercle `session_id`, target chat/user, expiry, status (`pending|approved|rejected|expired`), and `message_ids` for cleanup.
  - Polling uses adaptive intervals and backoff (to avoid stampedes under load).

### Per-group configuration
- `groups` (`Group`)
  - Verification: `verification_enabled`, `verification_timeout`, `kick_unverified`
  - Join gate: `join_gate_enabled`
  - Anti-flood: `antiflood_enabled`, `antiflood_limit`
  - Locks: `lock_links`, `lock_media`
  - Logs: `logs_enabled`, `logs_chat_id`, `logs_thread_id`
  - Welcome/Goodbye: `welcome_enabled`, `welcome_message`, `goodbye_enabled`, `goodbye_message`
  - Rules: `rules_text`
  - Moderation: `warn_limit`

### RBAC (custom roles per group)
- `permissions` (`Permission`)
  - Key: `group_id`, `telegram_id`, `role`
  - Flags used by `can_user(...)`: `can_verify`, `can_kick`, `can_ban`, `can_warn`, `can_manage_settings`, `can_manage_locks`, `can_manage_roles`, `can_view_status`, `can_view_logs`
  - Additional flags exist in the model (notes/filters), but current handlers are Telegram-admin-only for those commands.

### Pending enforcement for a specific group/user
- `pending_join_verifications` (`PendingJoinVerification`)
  - `group_id`, `telegram_id`
  - `kind`: `post_join` (default) or `join_request` (join-gate)
  - `status`: `pending`, `approved`, `rejected`, `timed_out`, `cancelled`
  - `expires_at`, `prompt_message_id`, `dm_message_id`, `mercle_session_id`, `decided_by`, `decided_at`
  - Join-request DM support: `user_chat_id`, `join_request_at`

Important invariant:
- There is a partial unique index `uq_pv_active` that enforces: only one active pending per `(group_id, telegram_id, kind)` when `status='pending'`. This is relied upon for concurrency safety in pending creation.

### Deep-link tokens
- `config_link_tokens` (`ConfigLinkToken`): `/start cfg_<token>` (DM settings), bound to `(group_id, admin_id)`, expires, one-time.
- `verification_link_tokens` (`VerificationLinkToken`): `/start ver_<token>` (DM verification panel), bound to `(pending_id, group_id, telegram_id)`, expires.

Telegram `/start` payload constraints:
- Telegram deep-link parameters are constrained (1–64 chars, limited charset). Tokens must remain within these constraints (the current implementation uses short URL-safe tokens).

### DM panel state (single-message UX)
- `dm_panel_state` (`DmPanelState`): remembers the last DM “panel” message id per `(telegram_id, panel_type, group_id)`.
- `group_wizard_state` (`GroupWizardState`): remembers setup wizard progress + setup-card message id.

### Group ↔ user mapping (for “silent user” moderation)
- `group_user_state` (`GroupUserState`) PK `(group_id, telegram_id)`
  - Stores username + names + timestamps + `last_source` + `join_count`
  - Used to resolve `@username` → `user_id` scoped to the current group.

### Moderation/content tables used by features
- Used by current handlers: `warnings`, `whitelist`, `admin_logs`, `flood_tracker`, `notes`, `filters`
- Present in schema but not currently used by handlers: `group_members`

## Permissions (actual checks)
File: `bot/utils/permissions.py`

`can_user(bot, chat_id, user_id, action)` returns `True` if:
- user is a Telegram admin (`creator`/`administrator`), OR
- user has a `permissions` row for that group with the relevant flag.

Actions used across handlers:
- `verify`, `kick` (also used for `mute`/`unmute`/`purge`), `ban` (also `unban`), `warn`
- `settings`, `locks`, `roles`, `status`, `logs`

## DM UX (commands, buttons, payloads)
File: `bot/handlers/commands.py`

### `/start` (no payload)
- Shows a “home” panel with buttons:
  - “Add to Group” (URL)
  - “Help”
  - “Status”
  - “Verify” (hidden if already globally verified)

### `/help` (DM)
- Shows a help panel (how to add the bot, how verification works, and the main commands).

### `/status` (DM)
- Shows the user’s global verification state (verified/not verified) and Mercle ID if present.

### `/verify`
- Starts Mercle verification in the current chat (DM recommended).

### `/start cfg_<token>` (open group settings in DM)
- Token is consumed (one-time). If invalid/expired → “Link expired. Run /menu again in the group.”

### `/start ver_<token>` (open DM join verification panel)
- Validates the token + pending row is still `pending` and not expired.
- Does NOT consume the token at open-time; it shows a panel:
  - “✅ Confirm” (`ver:<pending_id>:confirm`)
  - “Cancel” (`ver:<pending_id>:cancel`)

### `ver:<pending_id>:confirm`
- Idempotency:
  - If pending is already terminal or expired, the callback is a no-op (user sees “expired”).
  - Double-tap Confirm is prevented by a DB “starting” sentinel.
- Marks verification tokens “used” for that pending id, then starts Mercle verification “in-place” by editing the same DM message (`VerificationService.start_verification_panel(...)`).
- If Mercle session creation fails, the “starting” sentinel is cleared best-effort so the user can retry.

### `/menu`
- In group: checks `can_user(...,"settings")` and bot permissions (Restrict + Delete), then replies with a DM link `cfg_<token>`.
- In DM: shows a group picker of groups where you have `settings`.

### Settings screens & toggles (DM)
- Callback namespace: `cfg:<group_id>:...`
- Wizard (first-time per group): preset → verify on/off → logs destination.
- Home screens: Verification, Anti-spam, Locks, Logs.
- Verification screen includes:
  - Verify on/off (`cfg:<gid>:set:verify:on|off`)
  - Join gate on/off (`cfg:<gid>:set:join_gate:on|off`) with prerequisites:
    - group must have join requests enabled (`getChat(...).join_by_request == True`)
    - bot must have `can_invite_users == True` (required for approve/decline join requests)
  - The screen shows current prerequisite status (join requests / invite users) so misconfiguration is obvious.
  - Timeout buttons (2m/5m/10m)
  - Action on timeout (kick/mute)
- Anti-spam screen:
  - Anti-flood on/off + limit buttons.
- Locks screen:
  - Locks for links/media.
- Logs screen supports choosing a destination and “test log”; “choose channel/group” switches the DM into a `logs_setup` panel where the admin sends the target.

## Group UX & enforcement

### Setup card (when bot is added)
File: `bot/handlers/member_events.py`
- Posts/edits a setup card showing bot permissions (Restrict/Delete/Pin).
- Buttons:
  - `setup:recheck:<group_id>` (admin-only)
  - `setup:help`
- If the bot is ready, it tries to auto-delete the card after ~10 minutes; if deletion fails, it clears the buttons.

### Post-join verification (default: user joins but can’t talk)
File: `bot/handlers/member_events.py`
On member join:
1) Writes/updates `group_user_state` (`last_source="join"`).
2) If verification disabled → allow and send welcome (if configured).
3) If whitelisted in this group → allow and send welcome.
4) If globally verified → allow, mark group-user verified-seen, send welcome.
5) Else:
   - bot must be admin with Restrict
   - creates/reuses a `pending_join_verifications(kind="post_join")`
   - restricts the user from sending
   - sends a group prompt with:
     - deep-link URL to DM verification (`/start ver_<token>`)
     - admin override buttons `pv:<pending_id>:approve|reject`

Admin override buttons:
- Require `can_user(...,"verify")`.
- Approve: unrestrict + mark pending approved + delete/clear prompt + welcome.
- Reject: ban+unban (kick) + mark pending rejected + delete/clear prompt.

Why “delete/clear” exists:
- `deleteMessage` can fail (e.g., bot permissions, message older than ~48 hours). The implementation falls back to clearing buttons (edit reply markup) and optionally editing the text.

### Join gate (strict: user is not admitted until verified)
File: `bot/handlers/join_requests.py`
Preconditions:
- The group has join requests enabled in Telegram (`getChat(...).join_by_request == True`).
- The bot is an admin and has `can_invite_users` (required to approve/decline join requests).
- The group is configured with `groups.join_gate_enabled == True` (via DM settings).

Guardrail:
- If join gate is enabled but the bot can’t approve/decline join requests, the handler logs a “misconfigured” alert to the configured logs destination (if enabled) and (best-effort) DMs the user to contact admins, then returns without creating a pending.

On join request (only if `groups.join_gate_enabled == True`):
1) If verification disabled → approve join request.
2) Updates `group_user_state` (`last_source="join_request"`).
3) If whitelisted or globally verified → approve join request.
4) Else:
   - creates/reuses a `pending_join_verifications(kind="join_request")`
   - DMs the user a “Verify to Join” button using `chat_join_request.user_chat_id`
     - hard requirement: if `user_chat_id` is missing or the 5-minute join-request DM window is missed, the bot declines the request
   - If DM fails → declines join request and marks pending rejected.

On Mercle approval for `kind="join_request"`:
- Bot approves the join request and marks pending approved (Telegram errors are treated best-effort).

Cleanup:
- Expired join-request pendings are best-effort declined during periodic cleanup.

### Leave (goodbye)
File: `bot/handlers/member_events.py`
- Sends goodbye message if enabled/configured.

### Message enforcement (locks / anti-flood / filters / notes)
File: `bot/handlers/message_handlers.py`
- Runs only in groups/supergroups, ignores bots, and ignores `/commands`.
- Locks:
  - `lock_links`: deletes messages that look like links (entity-based URL detection + URL regex).
  - `lock_media`: deletes media messages (photo/video/document/etc).
- Anti-flood:
  - Uses `flood_tracker` with a 60s rolling window; if `antiflood_enabled` and `message_count > antiflood_limit`, the bot mutes the user for 5 minutes, deletes the triggering message, and posts a warning.
- Filters:
  - Uses `filters` table; a matched filter can reply with text, delete the message, or warn the user (depending on `filter_type`).
- Notes trigger:
  - If a message starts with `#note_name` and a note exists in `notes`, the bot replies with the stored content.

## Commands & UX (what exists today)

### Discovery
File: `bot/handlers/rbac_help.py`
- `/mycommands` (group-only) prints a role-aware list based on:
  - Telegram admin status OR
  - `permissions` flags (settings/status/warn/kick/locks/roles)

### Diagnostics
File: `bot/handlers/admin_commands.py`
- `/checkperms` (admins/settings users): checks bot permissions (Restrict/Delete/Pin) and join-gate prerequisites (join requests + Invite Users).
- `/status` (admins/status users): prints bot status info + DB counts.
- `/settings` (admins/settings users): view/update a subset of group settings from the group chat (DM settings UI is the primary UX).

### Moderation (reply-first patterns)
File: `bot/handlers/admin_commands.py`
- `/actions` (reply required): shows a callback-based action panel (Warn/Kick/Ban/Tempban/Mute/Unmute/Purge) for the replied user (no inline mode required).
- Direct commands exist for kick/ban/mute/unmute/warn/unban and resolve targets via:
  - reply → user id (best)
  - numeric id
  - `@username` via group admins list → `group_user_state` → best-effort `get_chat`
- Other moderation helpers:
  - `/warns` and `/resetwarns` (warnings)
  - `/whitelist` (bypass verification per-group)
  - `/pin` and `/unpin`
  - `/lock` and `/unlock` (links/media)

### Roles (custom RBAC)
File: `bot/handlers/admin_commands.py`
- `/roles` is Telegram-admin-only and supports:
  - list
  - add/remove
  - show
  - set `<perm>` on/off

### Content commands (notes/filters/rules/welcome)
File: `bot/handlers/content_commands.py`
- Notes:
  - `/save <name> <content>` (admin)
  - `/get <name>`
  - `/notes`
  - `/clear <name>` (admin)
  - `#<name>` trigger in chat (message handler)
- Filters:
  - `/filter <keyword> <response>` (admin) (type is configured per-command)
  - `/filters`
  - `/stop <keyword>` (admin) (remove)
- Welcome/Goodbye:
  - `/setwelcome <message>` (admin), `/welcome` (show)
  - `/setgoodbye <message>` (admin)
- Rules:
  - `/rules`
  - `/setrules <rules>` (admin)

## Telegram limitations that shape the design
- Bots can restrict what users can **send**, not what they can **read**:
  - Post-join verification can mute/restrict, but cannot hide chat history.
  - Join gate (join requests) is the only implemented mode that prevents a user from entering/reading the group before verification.
- Bots cannot enable “join requests” in the group settings; admins must enable it in Telegram.
- Bots cannot enumerate all members; `@username` moderation only works for users the bot has observed (join/join-request/DM verify).
