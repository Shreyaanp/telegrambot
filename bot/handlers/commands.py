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
from bot.utils.permissions import can_delete_messages, can_pin_messages, can_restrict_members, is_bot_admin, is_user_admin
from database.db import db
from database.models import GroupWizardState

logger = logging.getLogger(__name__)


def create_command_handlers(container: ServiceContainer) -> Router:
    router = Router()

    async def show_link_expired(chat_id: int, bot):
        await bot.send_message(chat_id=chat_id, text="Link expired. Run /menu again in the group.", parse_mode="HTML")

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
            await container.token_service.mark_verification_token_used(token)
            await open_dm_verification_panel(message.bot, container, user_id=user_id, pending_id=ver.pending_id)
            return

        await show_dm_home(message.bot, container, user_id=user_id)

    @router.message(Command("menu"))
    async def cmd_menu(message: Message):
        if message.chat.type == "private":
            await message.answer("To configure a group, run <code>/menu</code> in that group.", parse_mode="HTML")
            return

        if message.chat.type not in ["group", "supergroup"]:
            return

        group_id = message.chat.id
        admin_id = message.from_user.id
        await container.group_service.register_group(group_id, message.chat.title)

        if not await is_user_admin(message.bot, group_id, admin_id):
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

    @router.message(F.chat.type == "private", F.text)
    async def dm_fallback_text(message: Message):
        if message.text and message.text.startswith("/"):
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

        if not await is_user_admin(callback.bot, group_id, callback.from_user.id):
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
                # Placeholder: no routing implemented yet; keep as UX-only.
                await open_settings_screen(callback.bot, container, callback.from_user.id, group_id, "logs")
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
            await callback.answer()
            await callback.bot.edit_message_text(
                chat_id=callback.from_user.id,
                message_id=callback.message.message_id,
                text="<b>Verification</b>\nStarting Mercle…",
                parse_mode="HTML",
            )
            await container.verification_service.start_verification_panel(
                bot=callback.bot,
                telegram_id=callback.from_user.id,
                chat_id=callback.from_user.id,
                username=callback.from_user.username,
                group_id=int(pending.group_id),
                pending_id=pending_id,
                message_id=callback.message.message_id,
            )
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

    logs_on = "Off"  # placeholder until log destinations are implemented
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
            [InlineKeyboardButton(text="Moderation", callback_data=f"cfg:{group_id}:screen:moderation")],
            [InlineKeyboardButton(text="Logs", callback_data=f"cfg:{group_id}:screen:logs")],
            [InlineKeyboardButton(text="Advanced", callback_data=f"cfg:{group_id}:screen:advanced")],
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
            # Minimal implementation: record completion; logs routing is handled elsewhere.
            state.wizard_completed = True
            state.wizard_step = 3

    await open_settings_panel(bot, container, admin_id=admin_id, group_id=group_id)


async def open_settings_screen(bot, container: ServiceContainer, admin_id: int, group_id: int, screen: str):
    group = await container.group_service.get_or_create_group(group_id)
    if screen == "verification":
        text = f"<b>Verification</b> • {group.group_name or group_id}\n\nChoose:"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="On" if not group.verification_enabled else "On ✅", callback_data=f"cfg:{group_id}:set:verify:on"),
                    InlineKeyboardButton(text="Off" if group.verification_enabled else "Off ✅", callback_data=f"cfg:{group_id}:set:verify:off"),
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
        text = f"<b>Anti-spam</b> • {group.group_name or group_id}\n\nChoose:"
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
        text = f"<b>Logs</b> • {group.group_name or group_id}\n\nChoose:"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Off ✅", callback_data=f"cfg:{group_id}:set:logs:off"),
                    InlineKeyboardButton(text="This Group", callback_data=f"cfg:{group_id}:set:logs:group"),
                ],
                [InlineKeyboardButton(text="Choose Channel", callback_data=f"cfg:{group_id}:set:logs:channel")],
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
