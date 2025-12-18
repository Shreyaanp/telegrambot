"""Command handlers for the bot - DM home, secure /menu binding, and deep-link flows."""
from __future__ import annotations

import html
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from aiogram import F, Router
from aiogram.enums import ContentType
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

async def open_ticket_intake(bot, container: ServiceContainer, *, user_id: int, group_id: int) -> None:
    group = await container.group_service.get_or_create_group(group_id)
    title = group.group_name or str(group.group_id)
    text = (
        f"<b>Support ticket</b>\n"
        f"Group: {title}\n\n"
        "Send your message (one message for now)."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Cancel", callback_data=f"ticket:cancel:{group_id}")]]
    )
    await container.panel_service.upsert_dm_panel(
        bot=bot,
        user_id=user_id,
        panel_type="ticket_intake",
        group_id=group_id,
        text=text,
        reply_markup=kb,
    )


def create_command_handlers(container: ServiceContainer) -> Router:
    router = Router()

    async def show_link_expired(chat_id: int, bot):
        await bot.send_message(chat_id=chat_id, text="Link expired. Run /menu again in the group.", parse_mode="HTML")

    async def _touch_dm_subscriber(user) -> None:
        try:
            await container.dm_subscriber_service.touch(
                telegram_id=int(user.id),
                username=getattr(user, "username", None),
                first_name=getattr(user, "first_name", None),
                last_name=getattr(user, "last_name", None),
            )
        except Exception:
            return

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

    async def _get_active_ticket_intake_group_id(user_id: int) -> Optional[int]:
        async with db.session() as session:
            result = await session.execute(
                select(DmPanelState)
                .where(
                    DmPanelState.telegram_id == user_id,
                    DmPanelState.panel_type == "ticket_intake",
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

        await _touch_dm_subscriber(message.from_user)
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

        if payload and payload.startswith("sup_"):
            token = payload.replace("sup_", "", 1)
            sup = await container.token_service.consume_support_token(token, user_id=user_id)
            if not sup:
                await message.answer("Support link expired. Ask an admin to run /ticket again.", parse_mode="HTML")
                return
            await open_ticket_intake(message.bot, container, user_id=user_id, group_id=sup.group_id)
            return

        await show_dm_home(message.bot, container, user_id=user_id)

    @router.message(Command("ticket"))
    async def cmd_ticket(message: Message):
        if message.chat.type == "private":
            await message.answer("Open /ticket in the group where you need help.", parse_mode="HTML")
            return
        if message.chat.type not in ["group", "supergroup"]:
            return

        group_id = int(message.chat.id)
        user_id = int(message.from_user.id)
        await container.group_service.register_group(group_id, message.chat.title)

        group = await container.group_service.get_or_create_group(group_id)
        if not getattr(group, "logs_enabled", False) or not getattr(group, "logs_chat_id", None):
            await message.reply(
                "Support is not configured for this group.\n\n"
                "Admins: enable a logs destination in <code>/menu</code> → Logs.",
                parse_mode="HTML",
            )
            return

        bot_info = await message.bot.get_me()
        token = await container.token_service.create_support_token(group_id=group_id, user_id=user_id)
        deep_link = f"https://t.me/{bot_info.username}?start=sup_{token}"
        await message.reply(
            "Open support in DM:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Open Support", url=deep_link)]]),
        )

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
            await _touch_dm_subscriber(message.from_user)
            await show_dm_help(message.bot, container, user_id=message.from_user.id)
        else:
            await message.reply(
                "<b>Help</b>\n\n"
                "<b>Members</b>\n"
                "• <code>/rules</code> — show group rules\n"
                "• Reply <code>/report [reason]</code> — report to admins\n"
                "• <code>/ticket</code> — contact admins (opens DM)\n\n"
                "<b>Mods/Admins</b>\n"
                "• <code>/mycommands</code> — commands you can use\n"
                "• <code>/menu</code> — open settings in DM\n"
                "• <code>/checkperms</code> — bot permissions + join-gate readiness",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

    @router.message(Command("status"))
    async def cmd_user_status(message: Message):
        if message.chat.type != "private":
            return
        await _touch_dm_subscriber(message.from_user)
        await show_dm_status(message.bot, container, user_id=message.from_user.id)

    @router.message(Command("close"))
    async def cmd_close(message: Message):
        if message.chat.type != "private":
            return
        await _touch_dm_subscriber(message.from_user)
        active = await container.ticket_service.get_active_ticket(user_id=int(message.from_user.id))
        if not active:
            await message.answer("No open ticket.", parse_mode="HTML")
            return
        ticket_id = int(active["id"])
        await container.ticket_service.close_ticket(
            bot=message.bot,
            ticket_id=ticket_id,
            closed_by_user_id=int(message.from_user.id),
            notify_user=False,
            close_topic=True,
        )
        await message.answer(f"✅ Ticket <code>#{ticket_id}</code> closed.", parse_mode="HTML")

    @router.message(Command("unsubscribe"))
    @router.message(Command("stop"))
    async def cmd_unsubscribe(message: Message):
        if message.chat.type != "private":
            return
        await _touch_dm_subscriber(message.from_user)
        await container.dm_subscriber_service.set_opt_out(telegram_id=message.from_user.id, opted_out=True)
        await message.answer(
            "✅ Unsubscribed.\n\n"
            "You won't receive announcements in DM.\n"
            "Send <code>/subscribe</code> to opt back in.",
            parse_mode="HTML",
        )

    @router.message(Command("subscribe"))
    async def cmd_subscribe(message: Message):
        if message.chat.type != "private":
            return
        await container.dm_subscriber_service.set_opt_out(telegram_id=message.from_user.id, opted_out=False)
        await _touch_dm_subscriber(message.from_user)
        await message.answer(
            "✅ Subscribed.\n\n"
            "You'll receive announcements in DM.\n"
            "Send <code>/unsubscribe</code> to stop.",
            parse_mode="HTML",
        )

    @router.message(Command("verify"))
    async def cmd_verify(message: Message):
        user_id = message.from_user.id
        if message.chat.type == "private":
            await _touch_dm_subscriber(message.from_user)
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
        await _touch_dm_subscriber(message.from_user)
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

        await _touch_dm_subscriber(message.from_user)
        ticket_group_id = await _get_active_ticket_intake_group_id(message.from_user.id)
        if ticket_group_id:
            try:
                ticket_id = await container.ticket_service.create_ticket(
                    bot=message.bot,
                    group_id=int(ticket_group_id),
                    user_id=int(message.from_user.id),
                    message=str(message.text or ""),
                )
                await container.ticket_service.set_active_ticket(user_id=int(message.from_user.id), ticket_id=int(ticket_id))
                async with db.session() as session:
                    result = await session.execute(
                        select(DmPanelState).where(
                            DmPanelState.telegram_id == message.from_user.id,
                            DmPanelState.panel_type == "ticket_intake",
                            DmPanelState.group_id == int(ticket_group_id),
                        )
                    )
                    state = result.scalar_one_or_none()
                    if state:
                        await session.delete(state)
                await message.answer(
                    f"✅ Ticket <code>#{ticket_id}</code> created.\n\n"
                    "Send messages here to add updates.\n"
                    "Send <code>/close</code> to close the ticket.",
                    parse_mode="HTML",
                )
            except Exception as e:
                await message.answer(f"❌ Could not create ticket: {e}", parse_mode="HTML")
                await open_ticket_intake(message.bot, container, user_id=message.from_user.id, group_id=int(ticket_group_id))
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

        # If the user has an active open ticket, relay this DM to staff.
        try:
            active = await container.ticket_service.get_active_ticket(user_id=int(message.from_user.id))
        except Exception:
            active = None

        if active and active.get("status") == "open" and active.get("staff_chat_id") is not None:
            staff_chat_id = int(active["staff_chat_id"])
            thread_id = active.get("staff_thread_id")
            if thread_id is None:
                try:
                    group = await container.group_service.get_or_create_group(int(active.get("group_id") or 0))
                    thread_id = int(group.logs_thread_id) if getattr(group, "logs_thread_id", None) else None
                except Exception:
                    thread_id = None
            kwargs = {}
            if thread_id:
                kwargs["message_thread_id"] = int(thread_id)
            try:
                await message.bot.forward_message(
                    chat_id=staff_chat_id,
                    from_chat_id=int(message.chat.id),
                    message_id=int(message.message_id),
                    **kwargs,
                )
                return
            except Exception:
                pass

        await show_dm_home(message.bot, container, user_id=message.from_user.id)

    @router.message(F.chat.type == "private", F.content_type != ContentType.TEXT)
    async def dm_fallback_nontext(message: Message):
        # Ignore command-like captions
        if message.caption and message.caption.strip().startswith("/"):
            return

        await _touch_dm_subscriber(message.from_user)

        # If we're in ticket intake, create the ticket and then forward this message.
        ticket_group_id = await _get_active_ticket_intake_group_id(message.from_user.id)
        if ticket_group_id:
            try:
                caption = (message.caption or "").strip()
                seed = caption if caption else f"[{str(message.content_type)}]"
                ticket_id = await container.ticket_service.create_ticket(
                    bot=message.bot,
                    group_id=int(ticket_group_id),
                    user_id=int(message.from_user.id),
                    message=seed,
                )
                await container.ticket_service.set_active_ticket(user_id=int(message.from_user.id), ticket_id=int(ticket_id))
                async with db.session() as session:
                    result = await session.execute(
                        select(DmPanelState).where(
                            DmPanelState.telegram_id == message.from_user.id,
                            DmPanelState.panel_type == "ticket_intake",
                            DmPanelState.group_id == int(ticket_group_id),
                        )
                    )
                    state = result.scalar_one_or_none()
                    if state:
                        await session.delete(state)
                await message.answer(
                    f"✅ Ticket <code>#{ticket_id}</code> created.\n\n"
                    "Send messages here to add updates.\n"
                    "Send <code>/close</code> to close the ticket.",
                    parse_mode="HTML",
                )
            except Exception as e:
                await message.answer(f"❌ Could not create ticket: {e}", parse_mode="HTML")
                await open_ticket_intake(message.bot, container, user_id=message.from_user.id, group_id=int(ticket_group_id))
                return

        try:
            active = await container.ticket_service.get_active_ticket(user_id=int(message.from_user.id))
        except Exception:
            active = None
        if not active or active.get("status") != "open" or active.get("staff_chat_id") is None:
            return

        staff_chat_id = int(active["staff_chat_id"])
        thread_id = active.get("staff_thread_id")
        if thread_id is None:
            try:
                group = await container.group_service.get_or_create_group(int(active.get("group_id") or 0))
                thread_id = int(group.logs_thread_id) if getattr(group, "logs_thread_id", None) else None
            except Exception:
                thread_id = None
        kwargs = {}
        if thread_id:
            kwargs["message_thread_id"] = int(thread_id)
        try:
            await message.bot.forward_message(
                chat_id=staff_chat_id,
                from_chat_id=int(message.chat.id),
                message_id=int(message.message_id),
                **kwargs,
            )
        except Exception:
            return

    @router.callback_query(lambda c: c.data and c.data.startswith("ticket:"))
    async def ticket_callbacks(callback: CallbackQuery):
        if callback.message and callback.message.chat.type == "private":
            await _touch_dm_subscriber(callback.from_user)
        parts = callback.data.split(":")
        await callback.answer()
        if len(parts) < 2:
            return
        action = parts[1]
        if action == "cancel" and len(parts) >= 3:
            try:
                gid = int(parts[2])
            except ValueError:
                gid = None
            if gid is not None:
                async with db.session() as session:
                    result = await session.execute(
                        select(DmPanelState).where(
                            DmPanelState.telegram_id == callback.from_user.id,
                            DmPanelState.panel_type == "ticket_intake",
                            DmPanelState.group_id == gid,
                        )
                    )
                    state = result.scalar_one_or_none()
                    if state:
                        await session.delete(state)
            await show_dm_home(callback.bot, container, user_id=callback.from_user.id)

    @router.callback_query(lambda c: c.data and c.data.startswith("dm:"))
    async def dm_callbacks(callback: CallbackQuery):
        action = callback.data.split(":", 1)[1]
        if callback.message and callback.message.chat.type == "private":
            await _touch_dm_subscriber(callback.from_user)
        if action == "help":
            await callback.answer()
            await show_dm_help(callback.bot, container, user_id=callback.from_user.id)
        elif action == "home":
            await callback.answer()
            await show_dm_home(callback.bot, container, user_id=callback.from_user.id)
        elif action == "status":
            await callback.answer()
            await show_dm_status(callback.bot, container, user_id=callback.from_user.id)
        elif action == "verify":
            await callback.answer()
            if await container.user_manager.is_verified(callback.from_user.id):
                await callback.message.answer("✅ You are already verified.", parse_mode="HTML")
                return
            await container.verification_service.start_verification(
                bot=callback.bot,
                telegram_id=callback.from_user.id,
                chat_id=callback.from_user.id,
                username=callback.from_user.username,
            )
        elif action == "unsub":
            await container.dm_subscriber_service.set_opt_out(telegram_id=callback.from_user.id, opted_out=True)
            try:
                if callback.message:
                    await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await callback.answer("Unsubscribed")
        else:
            await callback.answer("Not allowed", show_alert=True)

    @router.callback_query(lambda c: c.data and c.data.startswith("cfg:"))
    async def cfg_callbacks(callback: CallbackQuery):
        if callback.message and callback.message.chat.type == "private":
            await _touch_dm_subscriber(callback.from_user)
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
            if key == "silent":
                await container.group_service.update_setting(group_id, silent_automations=(val == "on"))
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
        if callback.message and callback.message.chat.type == "private":
            await _touch_dm_subscriber(callback.from_user)
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

        if action == "rules_accept":
            group = await container.group_service.get_or_create_group(int(pending.group_id))
            require_rules = bool(getattr(group, "require_rules_acceptance", False)) and bool(
                str(getattr(group, "rules_text", "") or "").strip()
            )
            if not require_rules:
                await callback.answer()
                await open_dm_verification_panel(callback.bot, container, user_id=callback.from_user.id, pending_id=pending_id)
                return

            ok = await container.pending_verification_service.mark_rules_accepted(pending_id, callback.from_user.id)
            if not ok:
                await callback.answer("Link expired.", show_alert=True)
                return
            await callback.answer()
            await open_dm_verification_panel(callback.bot, container, user_id=callback.from_user.id, pending_id=pending_id)
            return

        if action.startswith("cap_"):
            group = await container.group_service.get_or_create_group(int(pending.group_id))
            if not bool(getattr(group, "captcha_enabled", False)):
                await callback.answer("Captcha is not enabled.", show_alert=True)
                await open_dm_verification_panel(callback.bot, container, user_id=callback.from_user.id, pending_id=pending_id)
                return

            style = str(getattr(group, "captcha_style", "button") or "button")
            max_attempts = int(getattr(group, "captcha_max_attempts", 3) or 3)
            await container.pending_verification_service.ensure_captcha(pending_id, callback.from_user.id, style=style)

            answer = action.replace("cap_", "", 1)
            res = await container.pending_verification_service.submit_captcha(
                pending_id,
                callback.from_user.id,
                answer=answer,
                max_attempts=max_attempts,
            )
            if not res:
                await callback.answer("Link expired.", show_alert=True)
                return

            status = str(res.get("status") or "")
            remaining = int(res.get("remaining") or 0)
            if status in ("solved", "already_solved"):
                await callback.answer()
                await open_dm_verification_panel(callback.bot, container, user_id=callback.from_user.id, pending_id=pending_id)
                return
            if status == "wrong":
                await callback.answer(f"❌ Wrong. Attempts left: {remaining}", show_alert=True)
                await open_dm_verification_panel(callback.bot, container, user_id=callback.from_user.id, pending_id=pending_id)
                return

            if status == "failed":
                # Mark terminal and enforce (best-effort).
                await container.pending_verification_service.decide(pending_id, status="rejected", decided_by=callback.from_user.id)
                try:
                    kind = str(getattr(pending, "kind", "post_join") or "post_join")
                    group_id = int(pending.group_id)
                    user_id = int(pending.telegram_id)

                    if kind == "join_request":
                        try:
                            await callback.bot.decline_chat_join_request(chat_id=group_id, user_id=user_id)
                        except Exception:
                            pass
                    else:
                        if bool(getattr(group, "kick_unverified", True)):
                            try:
                                await callback.bot.ban_chat_member(chat_id=group_id, user_id=user_id)
                                await callback.bot.unban_chat_member(chat_id=group_id, user_id=user_id)
                            except Exception:
                                pass
                    await container.pending_verification_service.edit_or_delete_group_prompt(callback.bot, pending, "❌ Captcha failed")
                except Exception:
                    pass

                await callback.answer()
                await callback.bot.edit_message_text(
                    chat_id=callback.from_user.id,
                    message_id=callback.message.message_id,
                    text="❌ Captcha failed. Ask an admin or try again later.",
                    parse_mode="HTML",
                )
                return

            await callback.answer("Captcha error. Try again.", show_alert=True)
            await open_dm_verification_panel(callback.bot, container, user_id=callback.from_user.id, pending_id=pending_id)
            return

        if action == "cancel":
            await callback.answer()
            await callback.bot.edit_message_text(
                chat_id=callback.from_user.id,
                message_id=callback.message.message_id,
                text="Cancelled. You can re-open the link from the group prompt.",
                parse_mode="HTML",
            )
            return

        if action == "confirm":
            # Idempotency: double-tap confirm should not start multiple Mercle sessions.
            group = await container.group_service.get_or_create_group(int(pending.group_id))
            require_rules = bool(getattr(group, "require_rules_acceptance", False)) and bool(
                str(getattr(group, "rules_text", "") or "").strip()
            )
            if require_rules and getattr(pending, "rules_accepted_at", None) is None:
                await callback.answer("Accept the rules first.", show_alert=True)
                await open_dm_verification_panel(callback.bot, container, user_id=callback.from_user.id, pending_id=pending_id)
                return
            if bool(getattr(group, "captcha_enabled", False)) and getattr(pending, "captcha_solved_at", None) is None:
                await callback.answer("Complete the captcha first.", show_alert=True)
                await open_dm_verification_panel(callback.bot, container, user_id=callback.from_user.id, pending_id=pending_id)
                return

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
        "3) Run <code>/menu</code> in the group (settings open in DM)\n\n"
        "<b>Moderation</b>\n"
        "• Reply in the group with <code>/actions</code>\n\n"
        "<b>Custom roles</b>\n"
        "• Telegram admins can grant roles in the group:\n"
        "  reply to a user → <code>/roles add moderator</code>"
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
            "Some groups may still require a verification step when you join/rejoin (use the link from the group prompt)."
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
        silent = bool(getattr(group, "silent_automations", False))
        text = (
            f"<b>Anti-spam</b> • {group.group_name or group_id}\n\n"
            f"Status: {'On ✅' if group.antiflood_enabled else 'Off'}\n"
            f"Limit: <code>{int(group.antiflood_limit or 10)}</code> msgs/min\n\n"
            f"Silent automations: {'On ✅' if silent else 'Off'}\n\n"
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
                    InlineKeyboardButton(
                        text="Silent: On ✅" if silent else "Silent: On",
                        callback_data=f"cfg:{group_id}:set:silent:on",
                    ),
                    InlineKeyboardButton(
                        text="Silent: Off ✅" if not silent else "Silent: Off",
                        callback_data=f"cfg:{group_id}:set:silent:off",
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
    group_title = str(group.group_name or group.group_id)
    rules_text = str(getattr(group, "rules_text", "") or "").strip()
    require_rules = bool(getattr(group, "require_rules_acceptance", False)) and bool(rules_text)

    # Step 1: rules acceptance.
    if require_rules and getattr(pending, "rules_accepted_at", None) is None:
        safe_rules = html.escape(rules_text)
        if len(safe_rules) > 1400:
            safe_rules = safe_rules[:1397] + "..."
        text = (
            f"<b>Verification</b>\n"
            f"Group: {html.escape(group_title)}\n\n"
            f"<b>Rules</b>\n{safe_rules}\n\n"
            f"Tap <b>I accept</b> to continue."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ I accept", callback_data=f"ver:{pending_id}:rules_accept")],
                [InlineKeyboardButton(text="Cancel", callback_data=f"ver:{pending_id}:cancel")],
            ]
        )
    else:
        # Step 2: optional captcha (blocks "Confirm" until solved).
        captcha_enabled = bool(getattr(group, "captcha_enabled", False))
        captcha_style = str(getattr(group, "captcha_style", "button") or "button")
        captcha_max_attempts = int(getattr(group, "captcha_max_attempts", 3) or 3)

        if captcha_enabled and getattr(pending, "captcha_solved_at", None) is None:
            ensured = await container.pending_verification_service.ensure_captcha(
                pending_id, user_id, style=captcha_style
            )
            pending = await container.pending_verification_service.get_pending(pending_id) or pending

            attempts = int(getattr(pending, "captcha_attempts", 0) or 0)
            remaining = max(0, int(captcha_max_attempts) - attempts)

            if not ensured:
                text = f"<b>Verification</b>\nGroup: {html.escape(group_title)}\n\nCaptcha expired."
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Cancel", callback_data=f"ver:{pending_id}:cancel")]])
            else:
                kind, expected = ensured
                kind = str(kind or "")
                expected = str(expected or "").strip().lower()
                status_line = f"Attempts left: <b>{remaining}</b>"
                if attempts:
                    status_line = f"Attempts used: <b>{attempts}</b> • left: <b>{remaining}</b>"

                if kind.startswith("math:"):
                    _, a_str, b_str = (kind.split(":", 2) + ["", ""])[:3]
                    try:
                        a = int(a_str)
                        b = int(b_str)
                    except Exception:
                        a = 2
                        b = 2
                    question = f"{a} + {b} = ?"
                    try:
                        exp_int = int(expected)
                    except Exception:
                        exp_int = a + b
                        expected = str(exp_int)
                    choices = {exp_int, exp_int + random.choice([1, 2, 3]), max(0, exp_int - random.choice([1, 2, 3]))}
                    while len(choices) < 3:
                        choices.add(exp_int + random.randint(-3, 3))
                    opts = [str(x) for x in choices]
                    random.shuffle(opts)
                    rows = []
                    for opt in opts:
                        rows.append([InlineKeyboardButton(text=opt, callback_data=f"ver:{pending_id}:cap_{opt}")])
                    rows.append([InlineKeyboardButton(text="Cancel", callback_data=f"ver:{pending_id}:cancel")])
                    kb = InlineKeyboardMarkup(inline_keyboard=rows)
                    text = (
                        f"<b>Verification</b>\n"
                        f"Group: {html.escape(group_title)}\n\n"
                        f"<b>Quick check</b>\n"
                        f"Solve: <code>{question}</code>\n"
                        f"{status_line}"
                    )
                else:
                    # button captcha
                    labels = {
                        "blue": "🟦 Blue",
                        "green": "🟩 Green",
                        "red": "🟥 Red",
                        "yellow": "🟨 Yellow",
                    }
                    colors = list(labels.keys())
                    if expected not in colors:
                        expected = "blue"
                    others = [c for c in colors if c != expected]
                    opts = [expected] + random.sample(others, k=2)
                    random.shuffle(opts)
                    rows = [[InlineKeyboardButton(text=labels[c], callback_data=f"ver:{pending_id}:cap_{c}")] for c in opts]
                    rows.append([InlineKeyboardButton(text="Cancel", callback_data=f"ver:{pending_id}:cancel")])
                    kb = InlineKeyboardMarkup(inline_keyboard=rows)
                    text = (
                        f"<b>Verification</b>\n"
                        f"Group: {html.escape(group_title)}\n\n"
                        f"<b>Quick check</b>\n"
                        f"Tap the <b>{expected.upper()}</b> button.\n"
                        f"{status_line}"
                    )
        else:
            # Step 3: ready to start Mercle.
            extra = []
            if require_rules:
                extra.append("✅ Rules accepted")
            if captcha_enabled:
                extra.append("✅ Captcha passed")
            extra_text = ("\n" + "\n".join(extra)) if extra else ""
            text = f"<b>Verification</b>\nGroup: {html.escape(group_title)}\n\nTap <b>Confirm</b> to start Mercle.{extra_text}"
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
