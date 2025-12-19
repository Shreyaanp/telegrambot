## Telegram Bot Flow Reference

This document maps how the bot runs, how data flows through the system, and where each flow lives in the codebase. All references below point to concrete modules/functions.

## Entry Points and Runtime Modes

- Polling mode (development):
  - Entry: `bot/main.py` (`main()`, `TelegramBot.run_polling`)
  - Flow: load config -> init services -> start polling.
- Webhook mode (production):
  - Entry: `webhook_server.py` (FastAPI app with `lifespan`)
  - Flow: create `TelegramBot` -> init -> set webhook -> accept updates at `WEBHOOK_PATH`.

Code references:
- `bot/main.py`
- `webhook_server.py`

## Configuration (How the bot is configured to run)

Configuration is loaded from environment variables in `bot/config.py`. The bot fails fast if required values are missing.

Required:
- `BOT_TOKEN`
- `DATABASE_URL`
- `MERCLE_API_URL`
- `MERCLE_API_KEY`

Optional (with defaults in `bot/config.py`):
- `MERCLE_API_SECRET`
- `MERCLE_APP_ID`
- `VERIFICATION_TIMEOUT` (seconds, default 300)
- `ACTION_ON_TIMEOUT` (kick or mute, default kick)
- `WEBHOOK_PATH` (default /webhook)
- `WEBHOOK_URL` (when set, indicates production/webhook mode)
- `ADMIN_API_TOKEN` (enables privileged admin API responses)
- `AUTO_DELETE_MESSAGES` (default true)
- `SEND_WELCOME_MESSAGE` (default true)

Database schema:
- Connection and schema checks: `database/db.py` (`db.connect`, `db.require_schema`)
- Migrations: `alembic/` (run `alembic upgrade head` against `DATABASE_URL` before running)

Code references:
- `bot/config.py`
- `database/db.py`
- `alembic/env.py`

## High Level Architecture

Services are wired in a dependency container and shared by all handlers.

- Service container: `bot/container.py`
- Core services: `bot/services/*` (verification, admin, rules, tickets, broadcasts, sequences, locks, etc.)
- Persistence models: `database/models.py`

Code references:
- `bot/container.py`
- `database/models.py`

## Inputs and Outputs

Inputs:
- Telegram updates (messages, commands, callbacks, join requests, member updates):
  - Polling: `Dispatcher.start_polling` in `bot/main.py`
  - Webhook: `webhook_server.py` (`webhook_handler`)
- Web requests (Mini App and admin endpoints):
  - `webhook_server.py` (`/app`, `/api/app/*`, `/health`, `/status`)
- Mercle API calls:
  - `bot/services/mercle_sdk.py` (create session, check status)

Outputs:
- Telegram actions: send/edit/delete messages, restrict/mute/ban/unban, approve/decline join requests.
- Database writes: users, groups, pending verifications, logs, rules, tickets, jobs, broadcasts.
- HTTP responses (FastAPI endpoints).
- Logs: stdout + `bot.log` (configured in `bot/main.py`).

Code references:
- `bot/main.py`
- `webhook_server.py`
- `bot/services/mercle_sdk.py`
- `database/models.py`

## Flow Details

### 1) Startup and shutdown

Flow:
1. Load env config.
2. Connect DB and verify schema.
3. Build service container.
4. Create bot, dispatcher, middleware.
5. Register handlers.
6. Start background tasks (cleanup, jobs).
7. Set Telegram command menu.

Code references:
- `bot/main.py` (`TelegramBot.initialize`, `TelegramBot.start`, `TelegramBot._periodic_cleanup`, `TelegramBot._jobs_worker`)
- `bot/middlewares/anonymous_admin_guard.py`

### 2) Webhook update handling

Flow:
1. Telegram POSTs updates to `WEBHOOK_PATH`.
2. Parse update and log summary.
3. Feed update to dispatcher.

Code references:
- `webhook_server.py` (`webhook_handler`, `_log_update_summary`)
- `bot/main.py` (handler registration order)

### 3) Handler registration and routing order

Order matters because the last router is a catch-all for messages.

Order in `bot/main.py`:
1. Commands: `bot/handlers/commands.py`
2. Admin commands: `bot/handlers/admin_commands.py`
3. Content commands: `bot/handlers/content_commands.py`
4. Ticket bridge: `bot/handlers/ticket_bridge.py`
5. Member events: `bot/handlers/member_events.py`
6. Admin join setup: `bot/handlers/member_events.py` (`create_admin_join_handlers`)
7. Leave events: `bot/handlers/member_events.py` (`create_leave_handlers`)
8. Join requests: `bot/handlers/join_requests.py`
9. RBAC help: `bot/handlers/rbac_help.py`
10. Message handlers (catch-all): `bot/handlers/message_handlers.py`

Code references:
- `bot/main.py`

### 4) Admin setup card when bot is added

Flow:
1. Bot is added to group (my_chat_member event).
2. Post setup card with required permissions.
3. Admin can re-check permissions.

Code references:
- `bot/handlers/member_events.py` (`create_admin_join_handlers`, `_send_or_update_setup_card`)

### 5) Settings and admin configuration (/menu)

Flow:
1. Admin runs `/menu` in group.
2. Bot creates short-lived config token and sends DM deep link.
3. Admin opens DM and `/start cfg_<token>` opens settings panel.
4. Settings updates are written to group settings and lock settings.

Code references:
- `bot/handlers/commands.py` (`cmd_menu`, `cmd_start`, `open_settings_panel`, `open_settings_screen`)
- `bot/services/token_service.py`
- `bot/services/panel_service.py`
- `bot/services/group_service.py`
- `bot/services/lock_service.py`

### 6) Verification flow (post-join)

Flow:
1. User joins group -> bot sees member update.
2. Apply federation ban, raid mode, and "no username" checks.
3. If verification enabled and not whitelisted, restrict user.
4. Create pending verification record and deep link.
5. Send group prompt with "Verify in DM" + admin approve/reject.
6. User opens DM link -> verification panel -> Mercle session.
7. On success, user is unmuted and pending is approved.
8. On failure/timeout, kick or mute per settings.

Code references:
- `bot/handlers/member_events.py` (`on_new_member`, pending prompt and buttons)
- `bot/services/pending_verification_service.py`
- `bot/services/verification.py`
- `bot/services/token_service.py`
- `bot/services/whitelist_service.py`
- `bot/services/federation_service.py`

### 7) Verification flow (join request / join gate)

Flow:
1. User requests to join (chat_join_request update).
2. Check join gate enabled and bot permissions.
3. Apply federation ban, raid mode, and "no username" checks.
4. Create pending verification and DM link (via `user_chat_id`).
5. User verifies in DM; on success bot approves join request.
6. On failure/timeout, bot declines join request.

Code references:
- `bot/handlers/join_requests.py`
- `bot/services/pending_verification_service.py`
- `bot/services/verification.py`
- `bot/services/token_service.py`

### 8) Verification flow (manual /verify)

Flow:
1. User runs `/verify` in DM or group.
2. Create Mercle session and send QR + link.
3. Poll Mercle for status; on success mark verified.

Code references:
- `bot/handlers/commands.py` (`cmd_verify`)
- `bot/services/verification.py` (`start_verification`, `_poll_verification`)
- `bot/services/mercle_sdk.py`
- `bot/services/user_manager.py`

### 9) DM verification panel (rules + captcha)

Flow:
1. User opens deep link `/start ver_<token>`.
2. DM panel shows rules acceptance if enabled.
3. Optional captcha (button or math).
4. On confirm, create Mercle session and poll.

Code references:
- `bot/handlers/commands.py` (`cmd_start`, `open_dm_verification_panel`, `ver_callbacks`)
- `bot/services/pending_verification_service.py`
- `bot/services/verification.py`

### 10) Periodic cleanup of expired verifications

Flow:
1. Background task runs every 60s.
2. Expire pending verifications.
3. Enforce kick/mute or decline join requests.

Code references:
- `bot/main.py` (`TelegramBot._periodic_cleanup`)
- `bot/services/pending_verification_service.py`

### 11) Anti-spam, filters, and notes

Flow:
1. Text message in group.
2. Enforce locks (links/media).
3. Anti-flood check -> mute and delete if needed.
4. Rules engine evaluation (reply/delete/warn/mute/log/sequence/ticket).
5. Keyword filters (delete/warn/auto-reply).
6. Hashtag notes (e.g. #rules).

Code references:
- `bot/handlers/message_handlers.py`
- `bot/services/antiflood_service.py`
- `bot/services/rules_service.py`
- `bot/services/filter_service.py`
- `bot/services/notes_service.py`
- `bot/services/admin_service.py`

### 12) Moderation actions and logs

Flow:
1. Admin runs moderation commands or uses `/actions` panel.
2. Permission check (Telegram admin or role).
3. Execute action (kick/ban/mute/warn).
4. Write admin log and optional log message to logs chat.

Code references:
- `bot/handlers/admin_commands.py`
- `bot/utils/permissions.py`
- `bot/services/admin_service.py`
- `bot/services/logs_service.py`
- `bot/services/roles_service.py`

### 13) Support tickets (user to staff bridge)

Flow:
1. User runs `/ticket` in group -> DM deep link is sent.
2. User sends message in DM -> ticket created -> staff topic or logs chat message.
3. Staff replies in topic -> bot relays to user DM.
4. Staff or user closes ticket.

Code references:
- `bot/handlers/commands.py` (`cmd_ticket`, `open_ticket_intake`)
- `bot/handlers/ticket_bridge.py`
- `bot/services/ticket_service.py`
- `bot/services/token_service.py`

### 14) Broadcasts and onboarding sequences (background jobs)

Flow:
1. Admin uses Mini App to create broadcast or onboarding steps.
2. Records stored and jobs enqueued.
3. Background job worker sends batches and reschedules on rate limits.

Code references:
- `webhook_server.py` (`app_group_broadcast`, `app_broadcast`, `app_broadcast_dm`, onboarding endpoints)
- `bot/main.py` (`TelegramBot._jobs_worker`)
- `bot/services/broadcast_service.py`
- `bot/services/sequence_service.py`
- `bot/services/jobs_service.py`

### 15) Mini App and web endpoints

Flow:
1. Mini App served at `/app` (static file).
2. Client calls `/api/app/*` endpoints with WebApp `initData`.
3. Server validates `initData`, checks permissions, and reads/writes group settings.

Code references:
- `webhook_server.py` (`/app`, `/api/app/*`)
- `bot/utils/webapp_auth.py`
- `static/app.html`

### 16) Health and status endpoints

Flow:
1. `/health` returns minimal status.
2. If `ADMIN_API_TOKEN` is provided, includes DB health.
3. `/status` returns detailed metrics (admin token required).

Code references:
- `webhook_server.py` (`/health`, `/status`)
- `bot/services/metrics_service.py`
- `database/db.py`

## Where Data Lives (high level)

- Users and verification sessions: `database/models.py` (`User`, `VerificationSession`)
- Group settings: `database/models.py` (`Group`)
- Pending verifications: `database/models.py` (`PendingJoinVerification`)
- Admin logs and warnings: `database/models.py` (`AdminLog`, `Warning`)
- Rules and actions: `database/models.py` (`Rule`, `RuleAction`)
- Tickets: `database/models.py` (`Ticket`, `TicketUserState`)
- Broadcasts and jobs: `database/models.py` (`Broadcast`, `BroadcastTarget`, `Job`)

Code references:
- `database/models.py`

## Notes on Permissions

- Telegram admin checks and custom roles are unified in `bot/utils/permissions.py`.
- Anonymous admins are guarded to avoid unsafe moderation calls.
- Role-aware command list is exposed via `/mycommands`.

Code references:
- `bot/utils/permissions.py`
- `bot/middlewares/anonymous_admin_guard.py`
- `bot/handlers/rbac_help.py`
