# `flow.md` (current codebase behavior)

This is the single source-of-truth documentation for what is implemented right now (no “future design”). It is derived by reading the code under `bot/` and `database/`.

Stack: `aiogram` bot + optional `FastAPI` webhook server + SQLite (`sqlite+aiosqlite`) via async SQLAlchemy.

## Runtime / entrypoints

### Bot wiring
File: `bot/main.py`
- Creates `Bot`, `Dispatcher`, DI container (`ServiceContainer`)
- Includes routers (message handlers are last so they don’t eat commands):
  - `bot/handlers/commands.py` (DM home/help, deep links, DM settings)
  - `bot/handlers/admin_commands.py` (moderation + roles + diagnostics)
  - `bot/handlers/content_commands.py` (notes/filters/rules/welcome)
  - `bot/handlers/member_events.py` (join/post-join verification, setup card, leave)
  - `bot/handlers/join_requests.py` (join-gate verification via join requests)
  - `bot/handlers/rbac_help.py` (`/mycommands`)
  - `bot/handlers/message_handlers.py` (locks/antiflood/filters/notes triggers)
- Runs a cleanup loop every ~60s:
  - deletes/updates expired verification sessions
  - finds expired pending join verifications and (best-effort) declines expired join requests

### Webhook server mode
File: `webhook_server.py`
- FastAPI receives Telegram updates and forwards them into `Dispatcher.feed_update(...)`.
- Does not run a separate cleanup loop; cleanup runs inside `TelegramBot` to avoid duplicate workers.

## Database (tables + what they mean)
File: `database/models.py` (created/updated by `database/db.py`)

### Global verification
- `users` (`User`)
  - `telegram_id` (PK), `mercle_user_id` (unique), `username`, names, `verified_at`
  - Once present, the user is treated as “verified” across all groups.

### Per-group configuration
- `groups` (`Group`)
  - Verification: `verification_enabled`, `verification_timeout`, `kick_unverified`
  - Join gate: `join_gate_enabled`
  - Anti-flood: `antiflood_enabled`, `antiflood_limit`
  - Locks: `lock_links`, `lock_media`
  - Logs: `logs_enabled`, `logs_chat_id`, `logs_thread_id`
  - Welcome/Goodbye: `welcome_enabled`, `welcome_message`, `goodbye_enabled`, `goodbye_message`
  - Rules: `rules_text`

### RBAC (custom roles per group)
- `permissions` (`Permission`)
  - Key fields: `group_id`, `telegram_id`, `role`
  - Flags: `can_verify`, `can_kick`, `can_ban`, `can_warn`
  - Extra flags: `can_manage_settings`, `can_manage_locks`, `can_manage_roles`, `can_view_status`, `can_view_logs`

### Pending enforcement for a specific group/user
- `pending_join_verifications` (`PendingJoinVerification`)
  - `group_id`, `telegram_id`
  - `kind`: `post_join` (default) or `join_request` (join-gate)
  - `status`: `pending`, `approved`, `rejected`, `timed_out`, `cancelled`
  - `expires_at`, `prompt_message_id`, `dm_message_id`, `mercle_session_id`, `decided_by`, `decided_at`
  - Join-request DM support: `user_chat_id`, `join_request_at`

### Deep-link tokens
- `config_link_tokens` (`ConfigLinkToken`): `/start cfg_<token>` (DM settings), bound to `(group_id, admin_id)`, expires, one-time.
- `verification_link_tokens` (`VerificationLinkToken`): `/start ver_<token>` (DM verification panel), bound to `(pending_id, group_id, telegram_id)`, expires.

### DM panel state (single-message UX)
- `dm_panel_state` (`DmPanelState`): remembers the last DM “panel” message id per `(telegram_id, panel_type, group_id)`.
- `group_wizard_state` (`GroupWizardState`): remembers setup wizard progress + setup-card message id.

### Group ↔ user mapping (for “silent user” moderation)
- `group_user_state` (`GroupUserState`) PK `(group_id, telegram_id)`
  - Stores username + names + timestamps + `last_source` + `join_count`
  - Used to resolve `@username` → `user_id` scoped to the current group.

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
  - “Verify” (hidden if already globally verified)

### `/start cfg_<token>` (open group settings in DM)
- Token is consumed (one-time). If invalid/expired → “Link expired. Run /menu again in the group.”

### `/start ver_<token>` (open DM join verification panel)
- Validates the token + pending row is still `pending` and not expired.
- Does NOT consume the token at open-time; it shows a panel:
  - “✅ Confirm” (`ver:<pending_id>:confirm`)
  - “Cancel” (`ver:<pending_id>:cancel`)

### `ver:<pending_id>:confirm`
- Marks verification tokens “used” for that pending id, then starts Mercle verification “in-place” by editing the same DM message (`VerificationService.start_verification_panel(...)`).

### `/menu`
- In group: checks `can_user(...,"settings")` and bot permissions (Restrict + Delete), then replies with a DM link `cfg_<token>`.
- In DM: shows a group picker of groups where you have `settings`.

### Settings screens & toggles (DM)
- Callback namespace: `cfg:<group_id>:...`
- Wizard (first-time per group): preset → verify on/off → logs destination.
- Verification screen includes:
  - Verify on/off (`cfg:<gid>:set:verify:on|off`)
  - Join gate on/off (`cfg:<gid>:set:join_gate:on|off`) with prerequisites:
    - group must have join requests enabled (`getChat(...).join_by_request == True`)
    - bot must have `can_invite_users == True`
  - Timeout buttons (2m/5m/10m)
  - Action on timeout (kick/mute)
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
   - creates a `pending_join_verifications(kind="post_join")`
   - restricts the user from sending
   - sends a group prompt with:
     - deep-link URL to DM verification (`/start ver_<token>`)
     - admin override buttons `pv:<pending_id>:approve|reject`

Admin override buttons:
- Require `can_user(...,"verify")`.
- Approve: unrestrict + mark pending approved + delete/clear prompt + welcome.
- Reject: ban+unban (kick) + mark pending rejected + delete/clear prompt.

### Join gate (strict: user is not admitted until verified)
File: `bot/handlers/join_requests.py`
Precondition: the group is configured by admins to require join requests (“Approve new members”).

On join request (only if `groups.join_gate_enabled == True`):
1) If verification disabled → approve join request.
2) Updates `group_user_state` (`last_source="join_request"`).
3) If whitelisted or globally verified → approve join request.
4) Else:
   - creates a `pending_join_verifications(kind="join_request")`
   - DMs the user a “Verify to Join” button using `chat_join_request.user_chat_id`
     - hard requirement: if `user_chat_id` is missing or the 5-minute join-request DM window is missed, the bot declines the request
   - If DM fails → declines join request and marks pending rejected.

On Mercle approval for `kind="join_request"`:
- Bot approves the join request and marks pending approved.

Cleanup:
- Expired join-request pendings are best-effort declined during periodic cleanup.

### Leave (goodbye)
File: `bot/handlers/member_events.py`
- Sends goodbye message if enabled/configured.

## Commands & UX (what exists today)

### Discovery
File: `bot/handlers/rbac_help.py`
- `/mycommands` (group-only) prints a role-aware list based on:
  - Telegram admin status OR
  - `permissions` flags (settings/status/warn/kick/locks/roles)

### Diagnostics
File: `bot/handlers/admin_commands.py`
- `/checkperms` (admins/settings users): checks bot’s required permissions for that group.
- `/status` (admins/status users): prints bot status info.

### Moderation (reply-first patterns)
File: `bot/handlers/admin_commands.py`
- `/actions` (reply required): shows an inline action panel (kick/ban/mute/unmute/warn/purge flows).
- Direct commands exist for kick/ban/mute/unmute/warn/unban and resolve targets via:
  - reply → user id (best)
  - numeric id
  - `@username` via group admins list → `group_user_state` → best-effort `get_chat`

### Roles (custom RBAC)
File: `bot/handlers/admin_commands.py`
- `/roles` is Telegram-admin-only and supports:
  - list
  - add/remove
  - show
  - set `<perm>` on/off

### Content commands (notes/filters/rules/welcome)
File: `bot/handlers/content_commands.py`
- These commands are Telegram-admin-only (they use `@require_admin`).

## Telegram limitations that shape the design
- Bots can restrict what users can **send**, not what they can **read**:
  - Post-join verification can mute/restrict, but cannot hide chat history.
  - Join gate (join requests) is the only implemented mode that prevents a user from entering/reading the group before verification.
- Bots cannot enable “join requests” in the group settings; admins must enable it in Telegram.
- Bots cannot enumerate all members; `@username` moderation only works for users the bot has observed (join/join-request/DM verify).
