# Bot Flow & Implementation (End-to-End)

This document describes the current production flow that is implemented in this repo, and where it lives in code.

## High-level principles

- **Settings are DM-only**: group chats only get setup card, join prompts, moderation output, diagnostics.
- **Single-message panels**: DM “Home”, DM “Settings”, and DM “Verification” are edited in-place (stored by `DmPanelState`).
- **All buttons are permission-checked server-side**: callbacks check Telegram admin status and/or custom RBAC permissions.
- **Deep links expire**: `/menu` issues `cfg_<token>` tokens; join prompts issue `ver_<token>` tokens; tokens expire and are one-time.
- **Auto-cleanup**: setup cards and join prompts are edited or deleted after success/timeout.

## Data model

All tables are SQLAlchemy models in `database/models.py`.

### Existing core tables

- `users`: global verified users (Mercle-backed). Verification is global.
- `groups`: per-group configuration (`verification_enabled`, `verification_timeout`, `kick_unverified`, antiflood, locks, etc).
- `verification_sessions`: Mercle session tracking for `/verify` and join verification.
- `permissions`: per-group custom roles (RBAC), used when a user is not a Telegram admin.

### New flow tables

- `config_link_tokens`: short-lived, one-time **settings deep links** (`cfg_<token>`) bound to `(group_id, admin_id)`.
- `pending_join_verifications`: per-join pending record for `(group_id, telegram_id)` with prompt message IDs, expiry, and decision state.
- `verification_link_tokens`: short-lived **verification deep links** (`ver_<token>`) bound to `(pending_id, group_id, telegram_id)`.
- `dm_panel_state`: stores “single message panel” IDs per user/panel type (`home`, `settings`, `verification`) and optional `group_id`.
- `group_wizard_state`: one-time wizard completion + setup card message ID per group.
- `group_user_state`: per-group attribution/history (not per-group verification) for analytics/exports.

### SQLite migrations

This repo does not use Alembic. `database/db.py` contains lightweight SQLite additive migrations:

- Adds missing `groups.*` columns (e.g. `lock_links`, `lock_media`) if the DB existed before those columns.
- Adds missing `permissions.*` RBAC columns (e.g. `can_manage_settings`) if needed.

## 1) DM Home (anyone)

### Trigger

- User opens bot in DM: `/start` without payload, or any non-command DM text.

### Behavior

- Bot shows one DM Home panel:
  - title + short description
  - buttons: **Add to Group**, **Help**, **Verify** (Verify is hidden if already verified)

### Code

- `bot/handlers/commands.py`
  - `/start` DM default → `show_dm_home()`
  - DM fallback (`F.chat.type == private`) → `show_dm_home()`
  - DM buttons (`dm:*`) → `dm_callbacks()`
- Panel editing/storage: `bot/services/panel_service.py` (`PanelService.upsert_dm_panel`)
- Verification check: `bot/services/user_manager.py` (`UserManager.is_verified`)

## 2) Add bot to group (Setup Card)

### Trigger

- Bot added to group: chat member event.

### Behavior

- Bot posts one Setup Card with required permissions:
  - Restrict ✅/❌, Delete ✅/❌, Pin (optional)
  - buttons: **Re-check**, **Help**
- **Re-check** edits the same card with updated status.
- When complete, card becomes “✅ Ready…” and auto-deletes after ~10 minutes.

### Code

- `bot/handlers/member_events.py`
  - `create_admin_join_handlers()` → `on_bot_added()`
  - `_send_or_update_setup_card()` builds/edits the setup card and stores message id in `GroupWizardState`.

## 3) Secure binding (group-issued token)

### Trigger

- Admin runs `/menu` in a group.

### Behavior

- Bot checks:
  - chat is group/supergroup
  - caller is Telegram admin OR has custom permission `settings`
  - bot is admin and has Restrict + Delete
- Bot replies with “Open settings in DM:” + deep link `cfg_<token>`.
- Token is short-lived and one-time.

### Code

- `bot/handlers/commands.py`
  - `/menu` in group → `TokenService.create_config_token()` + deep link to `/start cfg_<token>`
- Token implementation: `bot/services/token_service.py` (`create_config_token`, `consume_config_token`)
- RBAC permission check: `bot/utils/permissions.py` (`has_role_permission(..., "settings")`)

## 4) DM Settings Panel (single persistent message)

### Trigger

- Admin taps the deep link → `/start cfg_<token>` in DM.

### Behavior

- If token invalid/expired/used: “Link expired. Run /menu again in the group.”
- If valid:
  - creates/updates one DM Settings Panel message
  - includes wizard (first-time only per group) and then shows top-level sections
- Panels are permission-checked live; losing admin/role makes actions “Not allowed”.

### Code

- `bot/handlers/commands.py`
  - `/start cfg_<token>` → `open_settings_panel()`
  - callbacks `cfg:*`:
    - wizard: `cfg:<gid>:wiz:*` → `handle_wizard_choice()`
    - top-level: `cfg:<gid>:screen:<name>` → `open_settings_screen()`
    - setting mutations: `cfg:<gid>:set:*`
- Wizard state storage: `database/models.py` `GroupWizardState`
- Panel persistence: `PanelService.upsert_dm_panel()`

Notes:

- “Logs destination” UI exists as a screen, but full routing to channels/threads is not implemented yet (placeholder).

## 5) Verification join flow (Mercle, robust)

### 5.1 Member joins group

#### Trigger

- New member joins a group.

#### Behavior

- If `verification_enabled=OFF`: do nothing.
- If user is already globally verified: allow and record attribution.
- Else:
  1) Create/ensure `pending_join_verifications` record (idempotent per user/group while still pending)
  2) Restrict (mute)
  3) Post one join prompt message:
     - “verify to chat” + remaining time
     - **Verify in DM** deep link `ver_<token>` bound to `(group_id, user_id)`
     - **Approve / Reject** (admins/mod roles only)

#### Code

- `bot/handlers/member_events.py`
  - `create_member_handlers()` → `on_new_member()`
  - creates pending via `PendingVerificationService.create_pending()`
  - restricts user
  - creates `ver_<token>` via `TokenService.create_verification_token()`
  - stores prompt message id via `PendingVerificationService.set_prompt_message_id()`

### 5.2 Member verifies in DM

#### Trigger

- User taps Verify in DM → `/start ver_<token>`

#### Behavior

- If token invalid/expired/used: “Verification expired. Ask an admin or rejoin.”
- If valid:
  - show one DM Verification panel with **Confirm** / **Cancel**
- Confirm starts Mercle verification in-place (edits the same message).
- On Mercle approved:
  - user is globally verified
  - user is un-restricted in group (existing behavior)
  - join prompt is deleted
  - attribution updated in `group_user_state`

#### Code

- `bot/handlers/commands.py`
  - `/start ver_<token>` → `open_dm_verification_panel()`
  - callbacks `ver:<pending_id>:confirm|cancel`
- Mercle single-message flow: `bot/services/verification.py` (`start_verification_panel`, `_poll_verification`)
- Pending update + prompt cleanup: `bot/services/pending_verification_service.py`

### 5.3 Timeout

#### Trigger

- `expires_at` reached while still pending.

#### Behavior

- Apply group timeout action:
  - kick (ban+unban) OR keep muted
- Join prompt edits to “⏱ Timed out” and auto-deletes later.

#### Code

- Webhook mode: `webhook_server.py` periodic task calls `PendingVerificationService.find_expired()` and applies action.
- Polling mode: `bot/main.py` periodic task does the same.

### 5.4 Admin override

#### Trigger

- Admin presses **Approve** or **Reject** on join prompt.

#### Behavior

- Permission checks: Telegram admin OR custom role with `verify`.
- Approve: unrestrict and delete prompt.
- Reject: kick and edit prompt → auto-delete later.

#### Code

- `bot/handlers/member_events.py` callback handler `pv:<pending_id>:approve|reject`

## 6) Moderation flow (RBAC)

### Trigger

- Admin/mod replies to a message with `/actions`.

### Behavior

- Opens single Actions panel.
- Kick/Ban require confirmation screen.
- RBAC: Telegram admin OR custom permissions (warn/kick/ban/etc).

### Code

- `bot/handlers/admin_commands.py`
  - `/actions` builds the panel
  - callbacks `act:*` implement confirmation screens and actions
- RBAC helpers: `bot/utils/permissions.py` (`has_role_permission`, `require_role_or_admin`)

Notes:

- Telegram slash command menu cannot be customized per custom role; only per “admin scope”.
  - To make RBAC discoverable, `/mycommands` shows commands available to the current user in the group.
  - Implemented in `bot/handlers/rbac_help.py`.

## 7) Anti-spam + Locks (automatic enforcement)

- Enforcement exists in `bot/handlers/message_handlers.py` and uses `lock_links/lock_media` plus antiflood service.
- Locks can also be changed via DM Settings “Locks” screen, or via `/lock` and `/unlock` (RBAC-protected).

## 8) Diagnostics

- `/checkperms`: returns compact bot permissions summary + buttons.
  - `bot/handlers/admin_commands.py` → `send_perm_check()`
- `/status`: admin or `can_view_status` role users.
  - `bot/handlers/admin_commands.py` → `cmd_status()`

## Known gaps (not yet implemented)

- Full “Logs destinations” routing (channel selection, thread support, audit messages).
- True per-role command menu in Telegram UI (not possible); `/mycommands` is the intended replacement.
- Some Settings screens are placeholders (`moderation`, `advanced`) and can be filled out per your final copy spec.

