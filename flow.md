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
  - `GET /app`: serves `static/app.html` (Telegram Mini App settings UI).
  - `GET /verify`: serves `static/verify.html` (deep-link helper for Mercle).
  - `GET /health`: always returns a minimal liveness payload; includes DB status only when `ADMIN_API_TOKEN` is set + provided.
  - `GET /status`: returns detailed metrics only when `ADMIN_API_TOKEN` is set + provided.
  - `POST /api/app/bootstrap`: validates Telegram WebApp `initData` and lists groups where the user can manage settings.
  - `POST /api/app/group/{group_id}/settings`: validates `initData` + permissions and applies group settings updates (join gate prerequisites enforced).
  - `POST /api/app/group/{group_id}/logs/test`: sends a “test log” message to the configured logs destination.
  - `POST /api/app/group/{group_id}/broadcast`: validates `initData` + permissions and queues (or schedules via `delay_seconds`) an announcement broadcast to that group.
  - `POST /api/app/broadcast`: validates `initData` and queues (or schedules via `delay_seconds`) an announcement broadcast to multiple groups the user can manage.
  - `POST /api/app/dm/subscribers`: returns the current deliverable DM subscriber count (opted-in).
  - `POST /api/app/broadcast/dm`: queues (or schedules via `delay_seconds`) an announcement DM broadcast to deliverable, non-opted-out DM subscribers.
  - `POST /api/app/group/{group_id}/broadcasts`: lists recent broadcasts that targeted this group (Mini App history).
  - `POST /api/app/group/{group_id}/onboarding`: configures the first step of a per-group onboarding DM sequence (legacy v1).
  - `POST /api/app/group/{group_id}/onboarding/get`: fetches the onboarding steps list for this group (Mini App editor).
  - `POST /api/app/group/{group_id}/onboarding/steps`: updates the onboarding steps list for this group (Mini App editor).
  - `POST /api/app/group/{group_id}/rules`: lists rules for that group (v1 rules engine).
  - `POST /api/app/group/{group_id}/rules/test`: dry-run a sample message against current rules (Mini App test console).
  - `POST /api/app/group/{group_id}/rules/create`: creates a simple rule (contains/regex → reply/delete/warn/mute/log/start_sequence/create_ticket).
  - `POST /api/app/group/{group_id}/rules/delete`: deletes a rule.
  - `POST /api/app/group/{group_id}/tickets`: lists recent tickets for that group (Mini App queue view).
  - `POST /api/app/group/{group_id}/analytics`: read-only group analytics (pending joins, verification sessions, warnings, admin actions, federation summary).
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
- Sets Telegram command menus (Telegram scopes only; cannot be customized per custom role) via `set_my_commands(...)`:
  - Private chats: `/start`, `/help`, `/status`, `/verify`, `/menu`, `/subscribe`, `/unsubscribe`
  - Group chats (everyone): `/help`, `/rules`, `/report`, `/ticket`, `/mycommands`
  - Group chat admins (Telegram admins only): `/menu`, `/actions`, `/checkperms`, `/status`, `/modlog`, `/raid`, `/fed`, `/fban`, `/funban`, `/mycommands`, `/kick`, `/ban`, `/unban`, `/mute`, `/unmute`, `/warn`, `/roles`, `/whitelist`, `/lock`, `/unlock`
- If `WEBHOOK_URL` is set, the bot also sets a global chat menu button pointing to `<WEBHOOK_URL>/app` (Mini App settings UI).

### Logging (what you will and won’t see)
- `bot/main.py` logs to stdout and `bot.log` (and under systemd you can always use `journalctl -u telegrambot -f`).
- `webhook_server.py` logs a safe per-update summary:
  - commands are logged as `cmd=/...`
  - callback queries are logged as `data=...` (truncated) so button flows can be debugged
  - join requests include `user_chat_id=...` so join-gate DM eligibility is visible
  - chat member updates include `actor`, `target`, and `old->new` status transitions
  - private non-command messages log only `text_len=...`
  - raw user message text is never logged; non-command group messages log only metadata (`ct=...` and `text_len=...`)

### Periodic cleanup
File: `bot/main.py`
- Runs every ~60s (started by `TelegramBot.start()`, so it runs in both polling + webhook mode):
  - Marks expired `verification_sessions` as `expired` (does not delete rows).
  - Finds expired `pending_join_verifications` and:
    - `kind="join_request"`: best-effort declines the join request, marks pending `timed_out`.
    - `kind="post_join"`: kicks (ban+unban) if `groups.kick_unverified`, otherwise keeps user muted; marks pending `timed_out` and edits/deletes the group prompt best-effort.

### Background jobs
File: `bot/main.py`
- Runs a small DB-backed jobs worker loop (every ~2s when idle) for async features like broadcasts.
- Jobs are stored in `jobs` and the first implemented job is `broadcast_send`.
- Sequences also use jobs (`sequence_step`) for delayed sends.
- On Telegram rate limits (`RetryAfter` / 429), jobs are rescheduled with jitter + exponential backoff to avoid “429 storms”.

## Database (tables + what they mean)
File: `database/models.py` (migrated via Alembic)

Runtime:
- `DATABASE_URL` is required (no SQLite fallback).
- Schema is created via Alembic migrations (no runtime migrations); deploy runs `alembic upgrade head`.
- On startup, the bot requires `alembic_version` to exist (`db.require_schema()`), and fails fast if the schema wasn’t migrated.

### Global verification
- `users` (`User`)
  - `telegram_id` (PK), `mercle_user_id` (unique), username/names, `verified_at`
  - Global Mercle identity cache (who has verified at least once).
  - If a Mercle identity is already linked to a different Telegram account, the bot treats that verification as rejected (gate remains enforced).
  - Group access is still enforced via per-join verification flows (unless whitelisted or verification is disabled for that group).

### Mercle verification sessions (polling state)
- `verification_sessions` (`VerificationSession`)
  - Tracks Mercle `session_id`, target chat/user, expiry, status (`pending|approved|rejected|expired`), and `message_ids` for cleanup.
  - Polling uses adaptive intervals and backoff (to avoid stampedes under load).

### Operational metrics
- `metric_counters` (`MetricCounter`)
  - Persistent counters (survive restarts) used for admin `/status` metrics: admin actions, verification outcomes, API error counts.

### Background jobs + broadcasts
- `jobs` (`Job`)
  - Minimal DB-backed queue: `job_type`, `status`, `run_at`, attempts/locks, JSON payload.
- `broadcasts` (`Broadcast`)
  - Broadcast campaign record + progress counts (includes `scheduled_at` for delayed sends).
- `broadcast_targets` (`BroadcastTarget`)
  - Per-chat delivery state for a broadcast (`pending|sent|failed`).
- `dm_subscribers` (`DmSubscriber`)
  - Tracks DM deliverability + opt-out for DM broadcasts (DM interactions create/update rows).
  - Key fields: `telegram_id`, `opted_out`, `deliverable`, `fail_count`, `last_error`, timestamps (`last_seen_at`, `last_ok_at`, `last_fail_at`).

### Sequences (drip/onboarding)
- `sequences` (`Sequence`)
  - Per-group sequence definition with a stable `key` and a `trigger` (current trigger used: `user_verified`).
- `sequence_steps` (`SequenceStep`)
  - Ordered steps with a `delay_seconds` and message content.
- `sequence_runs` (`SequenceRun`)
  - A per-user execution of a sequence (idempotent per `trigger_key`).
- `sequence_run_steps` (`SequenceRunStep`)
  - Per-step delivery state; each pending step schedules a `sequence_step` job at `run_at`.

### Rules engine (v1)
- `rules` (`Rule`)
  - Per-group rules with a trigger (currently: `message_group`), a match (`contains|regex`), and priority/stop flags.
- `rule_actions` (`RuleAction`)
  - Ordered actions for a rule (current actions used: `reply|delete|warn|mute|log|start_sequence|create_ticket`).

### Federations (shared banlists)
- `federations` (`Federation`)
  - Federation record (shared moderation scope) with `name` and `owner_id`.
- `federation_bans` (`FederationBan`)
  - Federation ban entries (`federation_id`, `telegram_id`, `reason`, `banned_by`, `banned_at`).
- `groups.federation_id`
  - Each group can be attached to at most one federation; banned users are blocked on join and join-requests.

### Per-group configuration
- `groups` (`Group`)
  - Verification: `verification_enabled`, `verification_timeout`, `kick_unverified`
  - Verification gates: `require_rules_acceptance`, `captcha_enabled`, `captcha_style`, `captcha_max_attempts`
  - Join-quality: `block_no_username`
  - Join gate: `join_gate_enabled`
  - Anti-flood: `antiflood_enabled`, `antiflood_limit`
  - Locks: `lock_links`, `lock_media`
  - Logs: `logs_enabled`, `logs_chat_id`, `logs_thread_id`
  - Welcome/Goodbye: `welcome_enabled`, `welcome_message`, `goodbye_enabled`, `goodbye_message`
  - Rules: `rules_text`
  - Moderation: `warn_limit`, `silent_automations`, `raid_mode_until`
  - Federation: `federation_id`

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
  - DM gates state: `rules_accepted_at`, `captcha_kind`, `captcha_expected`, `captcha_attempts`, `captcha_solved_at`
  - Join-request DM support: `user_chat_id`, `join_request_at`

Important invariant:
- There is a partial unique index `uq_pv_active` that enforces: only one active pending per `(group_id, telegram_id, kind)` when `status='pending'`. This is relied upon for concurrency safety in pending creation.

### Deep-link tokens
- `config_link_tokens` (`ConfigLinkToken`): `/start cfg_<token>` (DM settings), bound to `(group_id, admin_id)`, expires, one-time.
- `verification_link_tokens` (`VerificationLinkToken`): `/start ver_<token>` (DM verification panel), bound to `(pending_id, group_id, telegram_id)`, expires.
- `support_link_tokens` (`SupportLinkToken`): `/start sup_<token>` (DM support ticket intake), bound to `(group_id, user_id)`, expires, one-time.

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
- Used by current handlers: `warnings`, `whitelist`, `admin_logs`, `flood_tracker`, `notes`, `filters`, `tickets`
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

### `/subscribe` / `/unsubscribe` (DM)
- Opt-in/out of DM announcement broadcasts.
- `/stop` is an alias for `/unsubscribe`.
- DM broadcasts include an “Unsubscribe” inline button (`dm:unsub`).

### `/close` (DM)
- Closes your currently active support ticket (if any).

### `/start cfg_<token>` (open group settings in DM)
- Token is consumed (one-time). If invalid/expired → “Link expired. Run /menu again in the group.”

### `/start ver_<token>` (open DM join verification panel)
- Validates the token + pending row is still `pending` and not expired.
- Does NOT consume the token at open-time; it shows a panel and may enforce optional DM gates before “Confirm” appears:
  - Rules acceptance (if enabled and `rules_text` is set): “✅ I accept” (`ver:<pending_id>:rules_accept`)
  - Captcha (if enabled): choices (`ver:<pending_id>:cap_<answer>`) for `button` or `math`
  - “✅ Confirm” (`ver:<pending_id>:confirm`)
  - “Cancel” (`ver:<pending_id>:cancel`) (closes the DM panel; pending remains active until expiry)

### `ver:<pending_id>:confirm`
- Idempotency:
  - If pending is already terminal or expired, the callback is a no-op (user sees “expired”).
  - Double-tap Confirm is prevented by a DB “starting” sentinel.
- Confirm is blocked until any configured DM gates (rules/captcha) are satisfied.
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
2) If group is in a federation and the user is federation-banned → bot bans the user (best-effort) and returns.
3) If raid mode is active (`groups.raid_mode_until > now`) and the user is not whitelisted/verified → bot kicks (ban+unban) and returns.
4) If `groups.block_no_username` is enabled and the user has no `@username` and is not whitelisted/verified → bot kicks (ban+unban) and returns.
5) If verification disabled → allow and send welcome (if configured).
6) If whitelisted in this group → allow and send welcome.
7) Else:
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

Promotion escape hatch:
- If a pending/restricted user is promoted to Telegram admin, the bot cancels any active pending verification for them and best-effort restores send permissions.

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
1) If group is in a federation and the user is federation-banned → bot declines the join request and returns.
2) If `groups.block_no_username` is enabled and the user has no `@username` and is not whitelisted/verified → bot declines the join request and returns (best-effort DM to user).
3) If verification disabled → approve join request.
4) Updates `group_user_state` (`last_source="join_request"`).
5) If raid mode is active (`groups.raid_mode_until > now`) and the user is not whitelisted/verified → decline join request (best-effort DM to try later).
6) If whitelisted → approve join request.
7) Else:
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
- If the leaving user had an active pending verification, it’s marked `cancelled` and the group prompt is removed best-effort.

### Message enforcement (locks / anti-flood / filters / notes)
File: `bot/handlers/message_handlers.py`
- Runs only in groups/supergroups, ignores bots, and ignores `/commands`.
- Updates `group_user_state` on messages (throttled) to improve `@username` → `user_id` resolution later.
- Locks:
  - `lock_links`: deletes messages/captions that look like links (entity-based URL detection + URL regex).
  - `lock_media`: deletes media messages (photo/video/document/sticker/poll/etc).
- Anti-flood:
  - Uses `flood_tracker` with a 60s rolling window; if `antiflood_enabled` and `message_count > antiflood_limit`, the bot mutes the user for 5 minutes and deletes the triggering message.
  - If `groups.silent_automations` is off, it also posts a warning message in chat.
- Rules engine (v1):
  - Evaluates enabled rules in `rules` (trigger `message_group`) before filters/notes; actions can reply/delete/warn/mute/log/start_sequence/create_ticket and may stop further processing.
- Filters:
  - Uses `filters` table; a matched filter can reply with text, delete the message, or warn the user (depending on `filter_type`).
- Notes trigger:
  - If a message starts with `#note_name` and a note exists in `notes`, the bot replies with the stored content.

## Commands & UX (what exists today)

### Discovery
File: `bot/handlers/rbac_help.py`
- `/mycommands` (group-only) prints a role-aware list based on:
  - Telegram admin status OR
  - `permissions` flags (settings/status/logs/warn/kick/ban/verify/locks)

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
  - `/report` (reply): sends a user report to the configured logs destination (if enabled) and stores it in `admin_logs`
  - `/raid`: enables/disables raid mode (lockdown) to block untrusted new joins temporarily
  - `/fed`: federation attach/detach for this group (shared moderation scope)
  - `/fban` and `/funban`: ban/unban a user across all groups in the federation
  - `/ticket`: opens a DM support intake flow and creates a `tickets` row (requires logs destination enabled for the group)
    - If the logs destination is a forum and the bot can manage topics, it creates a dedicated topic per ticket and relays messages both ways.
  - `/warns` (self; moderators can view others) and `/resetwarns` (admins) (warnings)
  - `/whitelist` (bypass verification per-group)
  - `/modlog` (admins/log viewers): view recent `admin_logs` (`/modlog [limit]`, `/modlog action <x>`, `/modlog admin <id>`, etc.)
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
- Anonymous admins (“Remain anonymous”) send messages without a stable user identity (`from_user` may be missing), so admin commands are rejected with a prompt to disable anonymity.
