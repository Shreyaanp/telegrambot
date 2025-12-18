"""Command handlers for the bot - DM home, secure /menu binding, and deep-link flows."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.container import ServiceContainer
from bot.utils.permissions import can_delete_messages, can_pin_messages, can_restrict_members, can_user, has_role_permission, is_bot_admin, is_user_admin
from database.db import db
from database.models import DmPanelState, GroupWizardState

logger = logging.getLogger(__name__)

def logs_summary(group, group_id: int) -> str:
    if not getattr(group, "logs_enabled", False) or not getattr(group, "logs_chat_id", None):
        return "Off"
    try:
        dest = int(group.logs_chat_id)
    except Exception:
        return "On"
    if dest == int(group_id):
        return "This group"
    return "Channel/Group"

async def open_logs_setup(bot, container: ServiceContainer, *, admin_id: int, group_id: int) -> None:
    text = (
        "<b>Logs destination</b>\n\n"
        "Send me one of these:\n"
        "1) Forward a message from the target channel/group\n"
        "2) The channel @username\n"
        "3) A numeric chat id\n\n"
        "Note: I must be added to that chat (and admin for channels) to send logs."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Back", callback_data=f"cfg:{group_id}:screen:logs")],
            [InlineKeyboardButton(text="Cancel", callback_data=f"cfg:{group_id}:home")],
        ]
    )
    await container.panel_service.upsert_dm_panel(
        bot=bot,
        user_id=admin_id,
        panel_type="logs_setup",
        group_id=group_id,
        text=text,
        reply_markup=kb,
    )


def create_command_handlers(container: ServiceContainer) -> Router:
    router = Router()

    async def show_link_expired(chat_id: int, bot):
        await bot.send_message(chat_id=chat_id, text="Link expired. Run /menu again in the group.", parse_mode="HTML")

    async def _get_active_logs_setup_group_id(user_id: int) -> Optional[int]:
        async with db.session() as session:
            result = await session.execute(
                select(DmPanelState)
                .where(
                    DmPanelState.telegram_id == user_id,
                    DmPanelState.panel_type == "logs_setup",
                )
                .order_by(DmPanelState.updated_at.desc())
                .limit(1)
            )
            state = result.scalar_one_or_none()
            if not state:
                return None
            if state.updated_at and (datetime.utcnow() - state.updated_at).total_seconds() > 15 * 60:
                return None
            return int(state.group_id) if state.group_id is not None else None

    @router.message(CommandStart())
    async def cmd_start(message: Message):
        if message.chat.type != "private":
            return

        user_id = message.from_user.id
        payload = None
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1:
            payload = parts[1].strip()

        if payload and payload.startswith("cfg_"):
            token = payload.replace("cfg_", "", 1)
            cfg = await container.token_service.consume_config_token(token, admin_id=user_id)
            if not cfg:
                await show_link_expired(user_id, message.bot)
                return
            await open_settings_panel(message.bot, container, admin_id=user_id, group_id=cfg.group_id)
            return

        if payload and payload.startswith("ver_"):
            token = payload.replace("ver_", "", 1)
            ver = await container.token_service.get_verification_token(token)
            if not ver or ver.telegram_id != user_id:
                await message.answer("Verification expired. Ask an admin or rejoin.", parse_mode="HTML")
                return
            pending = await container.pending_verification_service.get_pending(ver.pending_id)
            if not pending or pending.status != "pending":
                await message.answer("Verification expired. Ask an admin or rejoin.", parse_mode="HTML")
                return
            if pending.expires_at < datetime.utcnow():
                await message.answer("Verification expired. Ask an admin or rejoin.", parse_mode="HTML")
                return
            # Persist a durable (group_id, user_id) link from this DM verification entry-point.
            await container.pending_verification_service.touch_group_user(
                int(ver.group_id),
                user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                source="dm_verify",
                increment_join=False,
            )
            await open_dm_verification_panel(message.bot, container, user_id=user_id, pending_id=ver.pending_id)
            return

        await show_dm_home(message.bot, container, user_id=user_id)

    @router.message(Command("menu"))
    async def cmd_menu(message: Message):
        if message.chat.type == "private":
            groups = await container.group_service.list_groups()
            if not groups:
                await message.answer("No groups found yet. Add me to a group and run <code>/menu</code> there.", parse_mode="HTML")
                return

            user_id = message.from_user.id
            allowed = []
            for group in groups[:50]:
                group_id = int(group.group_id)
                try:
                    if await can_user(message.bot, group_id, user_id, "settings"):
                        allowed.append(group)
                except Exception:
                    continue

            if not allowed:
                await message.answer("I don't see any groups where you can manage settings yet. Run <code>/menu</code> in the group once.", parse_mode="HTML")
                return

            buttons = []
            for group in allowed[:12]:
                title = group.group_name or str(group.group_id)
                buttons.append([InlineKeyboardButton(text=title, callback_data=f"cfg:{int(group.group_id)}:home")])
            buttons.append([InlineKeyboardButton(text="Close", callback_data="dm:home")])
            await message.answer(
                "<b>Choose a group</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            )
            return

        if message.chat.type not in ["group", "supergroup"]:
            return

        group_id = message.chat.id
        admin_id = message.from_user.id
        await container.group_service.register_group(group_id, message.chat.title)

        is_admin = await is_user_admin(message.bot, group_id, admin_id)
        if not await can_user(message.bot, group_id, admin_id, "settings"):
            await message.reply("Admins only. Ask an admin to run /menu.", parse_mode="HTML")
            return

        if not await is_bot_admin(message.bot, group_id):
            await message.reply("I need to be admin. Run <code>/checkperms</code>.", parse_mode="HTML")
            return

        bot_info = await message.bot.get_me()
        restrict_ok = await can_restrict_members(message.bot, group_id, bot_info.id)
        delete_ok = await can_delete_messages(message.bot, group_id, bot_info.id)
        if not (restrict_ok and delete_ok):
            await message.reply("Missing permissions. Run <code>/checkperms</code>.", parse_mode="HTML")
            return

        token = await container.token_service.create_config_token(group_id=group_id, admin_id=admin_id)
        deep_link = f"https://t.me/{bot_info.username}?start=cfg_{token}"
        await message.reply(
            "Open settings in DM:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Open Settings", url=deep_link)]]),
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message):
        if message.chat.type == "private":
            await show_dm_help(message.bot, container, user_id=message.from_user.id)
        else:
            await message.reply("Use <code>/checkperms</code> or <code>/menu</code> in this group.", parse_mode="HTML")

    @router.message(Command("status"))
    async def cmd_user_status(message: Message):
        if message.chat.type != "private":
            return
        await show_dm_status(message.bot, container, user_id=message.from_user.id)

    @router.message(Command("verify"))
    async def cmd_verify(message: Message):
        user_id = message.from_user.id
        if await container.user_manager.is_verified(user_id):
            await message.answer("✅ You are already verified.", parse_mode="HTML")
            return
        await container.verification_service.start_verification(
            bot=message.bot,
            telegram_id=user_id,
            chat_id=message.chat.id,
            username=message.from_user.username,
        )

    @router.message(F.chat.type == "private", F.forward_from_chat)
    async def dm_logs_setup_forward(message: Message):
        group_id = await _get_active_logs_setup_group_id(message.from_user.id)
        if not group_id:
            return
        if not await can_user(message.bot, group_id, message.from_user.id, "settings"):
            await show_dm_home(message.bot, container, user_id=message.from_user.id)
            return
        chat = message.forward_from_chat
        if not chat or not chat.id:
            return
        await container.group_service.update_setting(group_id, logs_enabled=True, logs_chat_id=int(chat.id))
        await open_settings_screen(message.bot, container, admin_id=message.from_user.id, group_id=group_id, screen="logs")

    @router.message(F.chat.type == "private", F.text)
    async def dm_fallback_text(message: Message):
        if message.text and message.text.startswith("/"):
            return
        group_id = await _get_active_logs_setup_group_id(message.from_user.id)
        if group_id:
            if not await can_user(message.bot, group_id, message.from_user.id, "settings"):
                await show_dm_home(message.bot, container, user_id=message.from_user.id)
                return
            raw = (message.text or "").strip()
            dest_id: Optional[int] = None
            thread_id: Optional[int] = None
            if ":" in raw:
                left, right = raw.split(":", 1)
                raw = left.strip()
                try:
                    thread_id = int(right.strip())
                except ValueError:
                    thread_id = None
            if raw.startswith("@"):
                try:
                    chat = await message.bot.get_chat(raw)
                    dest_id = int(chat.id)
                except Exception:
                    dest_id = None
            else:
                try:
                    dest_id = int(raw)
                except ValueError:
                    dest_id = None
            if dest_id is None:
                await open_logs_setup(message.bot, container, admin_id=message.from_user.id, group_id=group_id)
                return
            await container.group_service.update_setting(group_id, logs_enabled=True, logs_chat_id=int(dest_id), logs_thread_id=thread_id)
            await open_settings_screen(message.bot, container, admin_id=message.from_user.id, group_id=group_id, screen="logs")
            return

        await show_dm_home(message.bot, container, user_id=message.from_user.id)

    @router.callback_query(lambda c: c.data and c.data.startswith("dm:"))
    async def dm_callbacks(callback: CallbackQuery):
        action = callback.data.split(":", 1)[1]
        await callback.answer()
        if action == "help":
            await show_dm_help(callback.bot, container, user_id=callback.from_user.id)
        elif action == "home":
            await show_dm_home(callback.bot, container, user_id=callback.from_user.id)
        elif action == "status":
            await show_dm_status(callback.bot, container, user_id=callback.from_user.id)
        elif action == "verify":
            if await container.user_manager.is_verified(callback.from_user.id):
                await callback.message.answer("✅ You are already verified.", parse_mode="HTML")
                return
            await container.verification_service.start_verification(
                bot=callback.bot,
                telegram_id=callback.from_user.id,
                chat_id=callback.from_user.id,
                username=callback.from_user.username,
            )
        else:
            await callback.answer("Not allowed", show_alert=True)

    @router.callback_query(lambda c: c.data and c.data.startswith("cfg:"))
    async def cfg_callbacks(callback: CallbackQuery):
        parts = callback.data.split(":")
        if len(parts) < 3:
            await callback.answer("Not allowed", show_alert=True)
            return
        _, group_str, action, *rest = parts
        try:
            group_id = int(group_str)
        except ValueError:
            await callback.answer("Not allowed", show_alert=True)
            return

        # Live permission check: Telegram admin OR custom role with settings access
        actor_id = callback.from_user.id
        if not await can_user(callback.bot, group_id, actor_id, "settings"):
            await callback.answer("Not allowed", show_alert=True)
            return

        if action == "close":
            await callback.answer()
            await show_dm_home(callback.bot, container, user_id=callback.from_user.id)
            return

        if action == "home":
            await callback.answer()
            await open_settings_panel(callback.bot, container, admin_id=callback.from_user.id, group_id=group_id)
            return

        if action == "wiz":
            await callback.answer()
            await handle_wizard_choice(callback.bot, container, callback.from_user.id, group_id, rest)
            return

        if action == "screen":
            if not rest:
                await callback.answer("Not allowed", show_alert=True)
                return
            await callback.answer()
            await open_settings_screen(callback.bot, container, admin_id=callback.from_user.id, group_id=group_id, screen=rest[0])
            return

        if action == "set":
            if len(rest) < 2:
                await callback.answer("Not allowed", show_alert=True)
                return
            key, val = rest[0], rest[1]
            await callback.answer()
            if key == "verify":
                await container.group_service.update_setting(group_id, verification_enabled=(val == "on"))
                await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "verification")
                return
            if key == "timeout":
                try:
                    seconds = int(val)
                except ValueError:
                    return
                await container.group_service.update_setting(group_id, verification_timeout=seconds)
                await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "verification")
                return
            if key == "join_gate":
                if val == "on":
                    # Join gate requires: join requests enabled + bot can approve/decline (can_invite_users).
                    try:
                        chat = await callback.bot.get_chat(group_id)
                        join_by_request = getattr(chat, "join_by_request", None)
                    except Exception:
                        join_by_request = None

                    if join_by_request is not True:
                        await callback.answer("Enable join requests in group settings first.", show_alert=True)
                        await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "verification")
                        return

                    try:
                        bot_info = await callback.bot.get_me()
                        bot_member = await callback.bot.get_chat_member(group_id, bot_info.id)
                        can_invite = bool(getattr(bot_member, "can_invite_users", False))
                    except Exception:
                        can_invite = False

                    if not can_invite:
                        await callback.answer("Grant the bot 'Invite Users' permission to manage join requests.", show_alert=True)
                        await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "verification")
                        return

                await container.group_service.update_setting(group_id, join_gate_enabled=(val == "on"))
                await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "verification")
                return
            if key == "action":
                await container.group_service.update_setting(group_id, action_on_timeout=("kick" if val == "kick" else "mute"))
                await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "verification")
                return
            if key == "antiflood":
                await container.group_service.update_setting(group_id, antiflood_enabled=(val == "on"))
                await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "antispam")
                return
            if key == "antiflood_limit":
                try:
                    limit = int(val)
                except ValueError:
                    return
                await container.group_service.update_setting(group_id, antiflood_limit=limit, antiflood_enabled=True)
                await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "antispam")
                return
            if key == "lock_links":
                await container.lock_service.set_lock(group_id, lock_links=(val == "on"))
                await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "locks")
                return
            if key == "lock_media":
                await container.lock_service.set_lock(group_id, lock_media=(val == "on"))
                await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "locks")
                return
            if key == "logs":
                if val == "off":
                    await container.group_service.update_setting(group_id, logs_enabled=False)
                    await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "logs")
                    return
                if val == "group":
                    await container.group_service.update_setting(group_id, logs_enabled=True, logs_chat_id=group_id, logs_thread_id=None)
                    await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "logs")
                    return
                if val == "channel":
                    await open_logs_setup(callback.bot, container, admin_id=callback.from_user.id, group_id=group_id)
                    return
                await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "logs")
                return
            if key == "logs_test":
                try:
                    group = await container.group_service.get_or_create_group(group_id)
                    if not getattr(group, "logs_enabled", False) or not getattr(group, "logs_chat_id", None):
                        await callback.bot.send_message(chat_id=callback.from_user.id, text="Logs are Off.", parse_mode="HTML")
                        return
                    dest_chat_id = int(group.logs_chat_id)
                    thread_id = int(group.logs_thread_id) if getattr(group, "logs_thread_id", None) else None
                    bot_info = await callback.bot.get_me()
                    try:
                        bot_member = await callback.bot.get_chat_member(dest_chat_id, bot_info.id)
                        if bot_member.status not in ("administrator", "creator", "member"):
                            raise RuntimeError(f"bot status: {bot_member.status}")
                    except Exception:
                        await callback.bot.send_message(
                            chat_id=callback.from_user.id,
                            text="I can't access that chat. Add me there (and make me admin for channels), then try again.",
                            parse_mode="HTML",
                        )
                        return
                    kwargs = {"disable_web_page_preview": True}
                    if thread_id:
                        kwargs["message_thread_id"] = thread_id
                    await callback.bot.send_message(
                        chat_id=dest_chat_id,
                        text=f"<b>Log test</b>\nGroup: <code>{group_id}</code>",
                        parse_mode="HTML",
                        **kwargs,
                    )
                    await callback.bot.send_message(chat_id=callback.from_user.id, text="✅ Sent a test log.", parse_mode="HTML")
                except Exception:
                    await callback.bot.send_message(chat_id=callback.from_user.id, text="❌ Failed to send test log.", parse_mode="HTML")
                return

        await callback.answer()
        await open_settings_panel(callback.bot, container, admin_id=callback.from_user.id, group_id=group_id)

    @router.callback_query(lambda c: c.data and c.data.startswith("ver:"))
    async def ver_callbacks(callback: CallbackQuery):
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Not allowed", show_alert=True)
            return
        _, pending_str, action = parts
        try:
            pending_id = int(pending_str)
        except ValueError:
            await callback.answer("Not allowed", show_alert=True)
            return

        pending = await container.pending_verification_service.get_pending(pending_id)
        if not pending or int(pending.telegram_id) != callback.from_user.id:
            await callback.answer("Not allowed", show_alert=True)
            return
        if pending.status != "pending" or pending.expires_at < datetime.utcnow():
            await callback.answer("Link expired. Run /menu again.", show_alert=True)
            return

        if action == "cancel":
            await container.pending_verification_service.decide(pending_id, status="cancelled", decided_by=callback.from_user.id)
            await callback.answer()
            await callback.bot.edit_message_text(
                chat_id=callback.from_user.id,
                message_id=callback.message.message_id,
                text="Cancelled.",
                parse_mode="HTML",
            )
            return

        if action == "confirm":
            # Idempotency: double-tap confirm should not start multiple Mercle sessions.
            ok = await container.pending_verification_service.try_mark_starting(pending_id, callback.from_user.id)
            if not ok:
                await callback.answer("Already started or expired.", show_alert=True)
                return

            await callback.answer()
            await container.token_service.mark_verification_tokens_used_for_pending(pending_id, callback.from_user.id)
            await callback.bot.edit_message_text(
                chat_id=callback.from_user.id,
                message_id=callback.message.message_id,
                text="<b>Verification</b>\nStarting Mercle…",
                parse_mode="HTML",
            )
            started = await container.verification_service.start_verification_panel(
                bot=callback.bot,
                telegram_id=callback.from_user.id,
                chat_id=callback.from_user.id,
                username=callback.from_user.username,
                group_id=int(pending.group_id),
                pending_id=pending_id,
                message_id=callback.message.message_id,
                pending_kind=getattr(pending, "kind", None),
            )
            if not started:
                await container.pending_verification_service.clear_starting_if_needed(pending_id, callback.from_user.id)
                try:
                    await callback.bot.edit_message_text(
                        chat_id=callback.from_user.id,
                        message_id=callback.message.message_id,
                        text="❌ Failed to start verification. Try again.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            return

    return router


def dm_home_text() -> str:
    return (
        "<b>MercleMerci</b>\n"
        "Group protection &amp; moderation.\n\n"
        "To configure: add me to a group, then run <code>/menu</code> there."
    )


def dm_home_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    add_link = f"https://t.me/{bot_username}?startgroup=true" if bot_username else ""
    rows = []
    if add_link:
        rows.append([InlineKeyboardButton(text="Add to Group", url=add_link)])
    rows.append([InlineKeyboardButton(text="Help", callback_data="dm:help")])
    rows.append([InlineKeyboardButton(text="Status", callback_data="dm:status")])
    rows.append([InlineKeyboardButton(text="Verify", callback_data="dm:verify")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dm_help_text() -> str:
    return (
        "<b>Help</b>\n"
        "1) Add me to a group\n"
        "2) Promote me to admin (Restrict, Delete)\n"
        "3) Run <code>/menu</code> in the group\n\n"
        "Moderate: reply with <code>/actions</code>."
    )


def dm_help_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    add_link = f"https://t.me/{bot_username}?startgroup=true" if bot_username else ""
    rows = []
    if add_link:
        rows.append([InlineKeyboardButton(text="Add to Group", url=add_link)])
    rows.append([InlineKeyboardButton(text="Back", callback_data="dm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def dm_status_text(*, is_verified: bool, mercle_user_id: str | None) -> str:
    if is_verified:
        mid = f"<code>{mercle_user_id}</code>" if mercle_user_id else "n/a"
        return (
            "<b>Status</b>\n"
            "✅ Verified\n\n"
            f"Mercle ID: {mid}\n\n"
            "This verification is global: you won’t need to verify again in other groups."
        )
    return (
        "<b>Status</b>\n"
        "❌ Not verified\n\n"
        "Tap <b>Verify</b> to start."
    )


def dm_status_keyboard(*, is_verified: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not is_verified:
        rows.append([InlineKeyboardButton(text="Verify", callback_data="dm:verify")])
    rows.append([InlineKeyboardButton(text="Back", callback_data="dm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_dm_status(bot, container: ServiceContainer, user_id: int):
    user = await container.user_manager.get_user(user_id)
    is_verified = user is not None
    text = dm_status_text(is_verified=is_verified, mercle_user_id=(user.mercle_user_id if user else None))
    kb = dm_status_keyboard(is_verified=is_verified)
    await container.panel_service.upsert_dm_panel(
        bot=bot,
        user_id=user_id,
        panel_type="home",
        text=text,
        reply_markup=kb,
    )


async def show_dm_home(bot, container: ServiceContainer, user_id: int):
    bot_info = await bot.get_me()
    is_verified = await container.user_manager.is_verified(user_id)
    kb = dm_home_keyboard(bot_info.username or "")
    if is_verified:
        kb.inline_keyboard = [row for row in kb.inline_keyboard if not (row and row[0].callback_data == "dm:verify")]
    await container.panel_service.upsert_dm_panel(
        bot=bot,
        user_id=user_id,
        panel_type="home",
        text=dm_home_text(),
        reply_markup=kb,
    )


async def show_dm_help(bot, container: ServiceContainer, user_id: int):
    bot_info = await bot.get_me()
    await container.panel_service.upsert_dm_panel(
        bot=bot,
        user_id=user_id,
        panel_type="home",
        text=dm_help_text(),
        reply_markup=dm_help_keyboard(bot_info.username or ""),
    )


async def open_settings_panel(bot, container: ServiceContainer, admin_id: int, group_id: int):
    group = await container.group_service.get_or_create_group(group_id)

    bot_info = await bot.get_me()
    restrict_ok = await can_restrict_members(bot, group_id, bot_info.id)
    delete_ok = await can_delete_messages(bot, group_id, bot_info.id)
    pin_ok = await can_pin_messages(bot, group_id, bot_info.id)
    bot_ok = "✅" if (restrict_ok and delete_ok) else "❌"

    # Wizard state
    async with db.session() as session:
        result = await session.execute(select(GroupWizardState).where(GroupWizardState.group_id == group_id))
        state = result.scalar_one_or_none()
        if not state:
            state = GroupWizardState(group_id=group_id, wizard_completed=False, wizard_step=1)
            session.add(state)

    if not state.wizard_completed:
        await render_wizard(bot, container, admin_id, group, state, bot_ok)
        return

    logs_on = logs_summary(group, group_id)
    text = (
        f"<b>Settings</b> • {group.group_name or group.group_id}\n"
        f"Verify: {'On' if group.verification_enabled else 'Off'}  Logs: {logs_on}  Bot: {bot_ok}\n\n"
        "Choose:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Verification", callback_data=f"cfg:{group_id}:screen:verification")],
            [InlineKeyboardButton(text="Anti-spam", callback_data=f"cfg:{group_id}:screen:antispam")],
            [InlineKeyboardButton(text="Locks", callback_data=f"cfg:{group_id}:screen:locks")],
            [InlineKeyboardButton(text="Logs", callback_data=f"cfg:{group_id}:screen:logs")],
            [InlineKeyboardButton(text="Close", callback_data=f"cfg:{group_id}:close")],
        ]
    )
    await container.panel_service.upsert_dm_panel(
        bot=bot,
        user_id=admin_id,
        panel_type="settings",
        group_id=group_id,
        text=text,
        reply_markup=kb,
    )


async def render_wizard(bot, container: ServiceContainer, admin_id: int, group, state: GroupWizardState, bot_ok: str):
    if state.wizard_step == 1:
        text = f"<b>Settings</b> • {group.group_name or group.group_id}\nBot: {bot_ok}\n\n<b>Step 1</b>: Preset"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Community", callback_data=f"cfg:{group.group_id}:wiz:preset:community"),
                    InlineKeyboardButton(text="Strict", callback_data=f"cfg:{group.group_id}:wiz:preset:strict"),
                ],
                [
                    InlineKeyboardButton(text="Support", callback_data=f"cfg:{group.group_id}:wiz:preset:support"),
                    InlineKeyboardButton(text="Custom", callback_data=f"cfg:{group.group_id}:wiz:preset:custom"),
                ],
                [InlineKeyboardButton(text="Close", callback_data=f"cfg:{group.group_id}:close")],
            ]
        )
    elif state.wizard_step == 2:
        text = f"<b>Settings</b> • {group.group_name or group.group_id}\nBot: {bot_ok}\n\n<b>Step 2</b>: Verification"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="On", callback_data=f"cfg:{group.group_id}:wiz:verify:on"),
                    InlineKeyboardButton(text="Off", callback_data=f"cfg:{group.group_id}:wiz:verify:off"),
                ],
                [InlineKeyboardButton(text="Close", callback_data=f"cfg:{group.group_id}:close")],
            ]
        )
    else:
        text = f"<b>Settings</b> • {group.group_name or group.group_id}\nBot: {bot_ok}\n\n<b>Step 3</b>: Logs"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Off", callback_data=f"cfg:{group.group_id}:wiz:logs:off"),
                    InlineKeyboardButton(text="This Group", callback_data=f"cfg:{group.group_id}:wiz:logs:group"),
                ],
                [InlineKeyboardButton(text="Choose Channel", callback_data=f"cfg:{group.group_id}:wiz:logs:channel")],
                [InlineKeyboardButton(text="Close", callback_data=f"cfg:{group.group_id}:close")],
            ]
        )

    await container.panel_service.upsert_dm_panel(
        bot=bot,
        user_id=admin_id,
        panel_type="settings",
        group_id=int(group.group_id),
        text=text,
        reply_markup=kb,
    )


async def handle_wizard_choice(bot, container: ServiceContainer, admin_id: int, group_id: int, rest: list[str]):
    if len(rest) < 2:
        return
    kind, choice = rest[0], rest[1]

    group = await container.group_service.get_or_create_group(group_id)

    async with db.session() as session:
        result = await session.execute(select(GroupWizardState).where(GroupWizardState.group_id == group_id))
        state = result.scalar_one_or_none()
        if not state:
            state = GroupWizardState(group_id=group_id, wizard_completed=False, wizard_step=1)
            session.add(state)

        if kind == "preset":
            if choice == "strict":
                await container.group_service.update_setting(group_id, verification_timeout=300, action_on_timeout="kick", antiflood_enabled=True, antiflood_limit=10, welcome_enabled=False, verification_enabled=True)
                await container.lock_service.set_lock(group_id, lock_links=True, lock_media=True)
            elif choice == "support":
                await container.group_service.update_setting(group_id, verification_timeout=600, action_on_timeout="mute", antiflood_enabled=True, antiflood_limit=20, welcome_enabled=True, verification_enabled=True)
                await container.lock_service.set_lock(group_id, lock_links=False, lock_media=False)
            elif choice == "community":
                await container.group_service.update_setting(group_id, verification_timeout=300, action_on_timeout="kick", antiflood_enabled=True, antiflood_limit=20, welcome_enabled=True, verification_enabled=True)
                await container.lock_service.set_lock(group_id, lock_links=False, lock_media=False)
            # custom: no changes
            state.wizard_step = 2

        elif kind == "verify":
            await container.group_service.update_setting(group_id, verification_enabled=(choice == "on"))
            if choice == "on":
                await container.group_service.update_setting(group_id, verification_timeout=300, action_on_timeout="kick")
            state.wizard_step = 3

        elif kind == "logs":
            if choice == "off":
                await container.group_service.update_setting(group_id, logs_enabled=False)
            elif choice == "group":
                await container.group_service.update_setting(group_id, logs_enabled=True, logs_chat_id=group_id)
            elif choice == "channel":
                state.wizard_completed = True
                state.wizard_step = 3
                await open_logs_setup(bot, container, admin_id=admin_id, group_id=group_id)
                return
            state.wizard_completed = True
            state.wizard_step = 3

    await open_settings_panel(bot, container, admin_id=admin_id, group_id=group_id)


async def open_settings_screen(bot, container: ServiceContainer, admin_id: int, group_id: int, screen: str):
    group = await container.group_service.get_or_create_group(group_id)
    if screen == "verification":
        join_by_request: bool | None = None
        can_invite_users: bool | None = None
        try:
            chat = await bot.get_chat(group_id)
            join_by_request = True if getattr(chat, "join_by_request", None) is True else False
        except Exception:
            join_by_request = None

        try:
            bot_info = await bot.get_me()
            bot_member = await bot.get_chat_member(group_id, bot_info.id)
            if bot_member.status == "creator":
                can_invite_users = True
            elif bot_member.status == "administrator":
                can_invite_users = bool(getattr(bot_member, "can_invite_users", False))
            else:
                can_invite_users = False
        except Exception:
            can_invite_users = None

        def _flag(ok: bool | None) -> str:
            if ok is True:
                return "✅"
            if ok is False:
                return "❌"
            return "❔"

        gate = "On ✅" if getattr(group, "join_gate_enabled", False) else "Off"
        text = (
            f"<b>Verification</b> • {group.group_name or group_id}\n\n"
            f"Require verification: {'On ✅' if group.verification_enabled else 'Off'}\n"
            f"Join requests: {_flag(join_by_request)}  Invite users: {_flag(can_invite_users)}\n"
            f"Join gate (requires join requests): {gate}"
        )

        warnings: list[str] = []
        if getattr(group, "join_gate_enabled", False):
            if join_by_request is not True:
                warnings.append("⚠️ Join requests are off; join gate won’t run.")
            if can_invite_users is False:
                warnings.append("⚠️ Bot missing Invite Users; join gate can’t approve/decline.")
        if warnings:
            text += "\n\n" + "\n".join(warnings)

        text += "\n\nChoose:"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="On" if not group.verification_enabled else "On ✅", callback_data=f"cfg:{group_id}:set:verify:on"),
                    InlineKeyboardButton(text="Off" if group.verification_enabled else "Off ✅", callback_data=f"cfg:{group_id}:set:verify:off"),
                ],
                [
                    InlineKeyboardButton(
                        text="Join gate: On ✅" if getattr(group, "join_gate_enabled", False) else "Join gate: On",
                        callback_data=f"cfg:{group_id}:set:join_gate:on",
                    ),
                    InlineKeyboardButton(
                        text="Join gate: Off ✅" if not getattr(group, "join_gate_enabled", False) else "Join gate: Off",
                        callback_data=f"cfg:{group_id}:set:join_gate:off",
                    ),
                ],
                [
                    InlineKeyboardButton(text="2m", callback_data=f"cfg:{group_id}:set:timeout:120"),
                    InlineKeyboardButton(text="5m", callback_data=f"cfg:{group_id}:set:timeout:300"),
                    InlineKeyboardButton(text="10m", callback_data=f"cfg:{group_id}:set:timeout:600"),
                ],
                [
                    InlineKeyboardButton(
                        text="Timeout: Kick ✅" if group.kick_unverified else "Timeout: Kick",
                        callback_data=f"cfg:{group_id}:set:action:kick",
                    ),
                    InlineKeyboardButton(
                        text="Keep muted ✅" if not group.kick_unverified else "Keep muted",
                        callback_data=f"cfg:{group_id}:set:action:mute",
                    ),
                ],
                [InlineKeyboardButton(text="Back", callback_data=f"cfg:{group_id}:home")],
            ]
        )
    elif screen == "antispam":
        text = (
            f"<b>Anti-spam</b> • {group.group_name or group_id}\n\n"
            f"Status: {'On ✅' if group.antiflood_enabled else 'Off'}\n"
            f"Limit: <code>{int(group.antiflood_limit or 10)}</code> msgs/min\n\n"
            "Tip: when a user exceeds the limit, the bot mutes them for 5 minutes."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="On ✅" if group.antiflood_enabled else "On",
                        callback_data=f"cfg:{group_id}:set:antiflood:on",
                    ),
                    InlineKeyboardButton(
                        text="Off ✅" if not group.antiflood_enabled else "Off",
                        callback_data=f"cfg:{group_id}:set:antiflood:off",
                    ),
                ],
                [
                    InlineKeyboardButton(text="Limit 10", callback_data=f"cfg:{group_id}:set:antiflood_limit:10"),
                    InlineKeyboardButton(text="Limit 20", callback_data=f"cfg:{group_id}:set:antiflood_limit:20"),
                ],
                [
                    InlineKeyboardButton(text="Limit 30", callback_data=f"cfg:{group_id}:set:antiflood_limit:30"),
                    InlineKeyboardButton(text="Limit 50", callback_data=f"cfg:{group_id}:set:antiflood_limit:50"),
                ],
                [InlineKeyboardButton(text="Back", callback_data=f"cfg:{group_id}:home")],
            ]
        )
    elif screen == "locks":
        lock_links, lock_media = await container.lock_service.get_locks(group_id)
        text = f"<b>Locks</b> • {group.group_name or group_id}\n\nChoose:"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"Links: {'On ✅' if lock_links else 'Off'}",
                        callback_data=f"cfg:{group_id}:set:lock_links:{'off' if lock_links else 'on'}",
                    ),
                    InlineKeyboardButton(
                        text=f"Media: {'On ✅' if lock_media else 'Off'}",
                        callback_data=f"cfg:{group_id}:set:lock_media:{'off' if lock_media else 'on'}",
                    ),
                ],
                [InlineKeyboardButton(text="Back", callback_data=f"cfg:{group_id}:home")],
            ]
        )
    elif screen == "logs":
        dest = "Off"
        if getattr(group, "logs_enabled", False) and getattr(group, "logs_chat_id", None):
            if int(group.logs_chat_id) == int(group_id):
                dest = "This group"
            else:
                dest = f"<code>{int(group.logs_chat_id)}</code>"
        thread = ""
        if getattr(group, "logs_enabled", False) and getattr(group, "logs_thread_id", None):
            thread = f"\nThread: <code>{int(group.logs_thread_id)}</code>"
        text = f"<b>Logs</b> • {group.group_name or group_id}\n\nCurrent: {dest}{thread}\n\nChoose:"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Off ✅" if not getattr(group, "logs_enabled", False) else "Off",
                        callback_data=f"cfg:{group_id}:set:logs:off",
                    ),
                    InlineKeyboardButton(
                        text="This Group ✅" if getattr(group, "logs_enabled", False) and getattr(group, "logs_chat_id", None) and int(group.logs_chat_id) == int(group_id) else "This Group",
                        callback_data=f"cfg:{group_id}:set:logs:group",
                    ),
                ],
                [InlineKeyboardButton(text="Choose Channel/Group…", callback_data=f"cfg:{group_id}:set:logs:channel")],
                [InlineKeyboardButton(text="Test log", callback_data=f"cfg:{group_id}:set:logs_test:now")],
                [InlineKeyboardButton(text="Back", callback_data=f"cfg:{group_id}:home")],
            ]
        )
    else:
        text = f"<b>{screen.title()}</b> • {group.group_name or group_id}\n\nNot implemented."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Back", callback_data=f"cfg:{group_id}:home")]])

    await container.panel_service.upsert_dm_panel(
        bot=bot,
        user_id=admin_id,
        panel_type="settings",
        group_id=group_id,
        text=text,
        reply_markup=kb,
    )


async def open_dm_verification_panel(bot, container: ServiceContainer, user_id: int, pending_id: int):
    pending = await container.pending_verification_service.get_pending(pending_id)
    if not pending or pending.status != "pending":
        await bot.send_message(chat_id=user_id, text="Verification expired. Ask an admin or rejoin.", parse_mode="HTML")
        return
    group = await container.group_service.get_or_create_group(int(pending.group_id))
    text = f"<b>Verification</b>\nGroup: {group.group_name or group.group_id}"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm", callback_data=f"ver:{pending_id}:confirm")],
            [InlineKeyboardButton(text="Cancel", callback_data=f"ver:{pending_id}:cancel")],
        ]
    )
    msg_id = await container.panel_service.upsert_dm_panel(
        bot=bot,
        user_id=user_id,
        panel_type="verification",
        group_id=int(pending.group_id),
        text=text,
        reply_markup=kb,
    )
    await container.pending_verification_service.set_dm_message_id(pending_id, msg_id)
