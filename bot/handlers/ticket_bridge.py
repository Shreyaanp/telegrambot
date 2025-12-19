"""Ticket bridge handlers (v2): relay between user DMs and staff forum topics."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.container import ServiceContainer
from database.db import db
from database.models import Ticket

logger = logging.getLogger(__name__)


def create_ticket_bridge_handlers(container: ServiceContainer) -> Router:
    router = Router()

    @router.callback_query(lambda c: c.data and c.data.startswith("tix:"))
    async def tix_callbacks(callback: CallbackQuery):
        parts = str(callback.data or "").split(":")
        if len(parts) < 3:
            await callback.answer("Not allowed", show_alert=True)
            return
        _, action, ticket_str = parts[:3]
        try:
            ticket_id = int(ticket_str)
        except Exception:
            await callback.answer("Not allowed", show_alert=True)
            return

        if action != "close":
            await callback.answer("Not allowed", show_alert=True)
            return

        # Ensure this button is being used in the staff chat for this ticket.
        staff_chat_id = None
        async with db.session() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket:
                staff_chat_id = int(ticket.staff_chat_id) if getattr(ticket, "staff_chat_id", None) is not None else None

        if staff_chat_id is not None and callback.message and int(callback.message.chat.id) != int(staff_chat_id):
            await callback.answer("Not allowed", show_alert=True)
            return

        await callback.answer()
        await container.ticket_service.close_ticket(
            bot=callback.bot,
            ticket_id=int(ticket_id),
            closed_by_user_id=int(callback.from_user.id),
            notify_user=True,
            close_topic=True,
        )
        try:
            if callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    @router.message(F.chat.type.in_(["group", "supergroup"]))
    async def relay_staff_to_user(message: Message):
        # Ignore bot messages (including the bot's own ticket creation post).
        if message.from_user and message.from_user.is_bot:
            return

        # Map message -> ticket via forum thread id first, then via reply-to.
        ticket = None
        try:
            thread_id = int(getattr(message, "message_thread_id", 0) or 0)
            if thread_id:
                ticket = await container.ticket_service.get_ticket_by_staff_thread(
                    staff_chat_id=int(message.chat.id),
                    thread_id=thread_id,
                )
        except Exception:
            ticket = None

        if not ticket and message.reply_to_message:
            try:
                ticket = await container.ticket_service.get_ticket_by_staff_message(
                    staff_chat_id=int(message.chat.id),
                    staff_message_id=int(message.reply_to_message.message_id),
                )
            except Exception:
                ticket = None

        if not ticket or ticket.get("status") != "open":
            return

        # Allow closing via /close for non-anonymous staff (anonymous admins should use the Close button).
        text = (message.text or "").strip()
        if text.startswith("/close"):
            if message.from_user is None:
                try:
                    await message.reply("Use the <b>Close ticket</b> button (anonymous admin cannot be verified).", parse_mode="HTML")
                except Exception:
                    pass
                return
            await container.ticket_service.close_ticket(
                bot=message.bot,
                ticket_id=int(ticket["id"]),
                closed_by_user_id=int(message.from_user.id),
                notify_user=True,
                close_topic=True,
            )
            return

        try:
            # Store staff message in history
            content = message.text or message.caption or ""
            message_type = "text"
            file_id = None
            if message.photo:
                message_type = "photo"
                file_id = message.photo[-1].file_id if message.photo else None
            elif message.video:
                message_type = "video"
                file_id = message.video.file_id
            elif message.document:
                message_type = "document"
                file_id = message.document.file_id
            elif message.voice:
                message_type = "voice"
                file_id = message.voice.file_id
            
            await container.ticket_service.add_message(
                ticket_id=int(ticket["id"]),
                sender_type="staff",
                sender_id=int(message.from_user.id) if message.from_user else None,
                sender_name=message.from_user.full_name if message.from_user else "Staff",
                message_type=message_type,
                content=content,
                file_id=file_id,
                telegram_message_id=int(message.message_id),
            )
            
            # Forward to user
            await message.bot.copy_message(
                chat_id=int(ticket["user_id"]),
                from_chat_id=int(message.chat.id),
                message_id=int(message.message_id),
            )
        except Exception as e:
            logger.warning(f"Failed to relay staff message for ticket {ticket['id']}: {e}")
            return

    return router

