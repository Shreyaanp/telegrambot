"""Ticket service - support tickets (v1 + forum-topic bridge v2)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from database.db import db
from database.models import Group, Ticket, TicketUserState, TicketMessage

logger = logging.getLogger(__name__)


class TicketService:
    async def add_message(
        self,
        *,
        ticket_id: int,
        sender_type: str,  # user|staff|system
        sender_id: int | None = None,
        sender_name: str | None = None,
        message_type: str = "text",
        content: str | None = None,
        file_id: str | None = None,
        telegram_message_id: int | None = None,
    ) -> int:
        """Store a message in the ticket conversation history."""
        now = datetime.utcnow()
        async with db.session() as session:
            msg = TicketMessage(
                ticket_id=int(ticket_id),
                sender_type=sender_type,
                sender_id=int(sender_id) if sender_id else None,
                sender_name=sender_name,
                message_type=message_type,
                content=content,
                file_id=file_id,
                telegram_message_id=int(telegram_message_id) if telegram_message_id else None,
                created_at=now,
            )
            session.add(msg)
            await session.flush()
            
            # Update ticket timestamps and message count
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket:
                ticket.last_message_at = now
                ticket.message_count = int(ticket.message_count or 0) + 1
                if sender_type == "staff":
                    ticket.last_staff_reply_at = now
                elif sender_type == "user":
                    ticket.last_user_message_at = now
            
            return int(msg.id)

    async def get_ticket_messages(self, *, ticket_id: int, limit: int = 50) -> list[dict]:
        """Retrieve conversation history for a ticket."""
        limit = max(1, min(int(limit or 50), 200))
        async with db.session() as session:
            result = await session.execute(
                select(TicketMessage)
                .where(TicketMessage.ticket_id == int(ticket_id))
                .order_by(TicketMessage.created_at.asc())
                .limit(limit)
            )
            messages = list(result.scalars().all())
            return [
                {
                    "id": int(m.id),
                    "sender_type": str(m.sender_type),
                    "sender_id": int(m.sender_id) if m.sender_id else None,
                    "sender_name": str(m.sender_name or ""),
                    "message_type": str(m.message_type),
                    "content": str(m.content or ""),
                    "file_id": str(m.file_id or ""),
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ]

    async def list_tickets(self, *, group_id: int, status: str = "open", limit: int = 20) -> list[dict]:
        status = str(status or "open")
        if status not in ("open", "closed"):
            status = "open"
        limit = max(1, min(int(limit or 20), 50))

        async with db.session() as session:
            result = await session.execute(
                select(Ticket)
                .where(Ticket.group_id == int(group_id), Ticket.status == status)
                .order_by(Ticket.created_at.desc(), Ticket.id.desc())
                .limit(limit)
            )
            tickets = list(result.scalars().all())
            out: list[dict] = []
            for t in tickets:
                out.append(
                    {
                        "id": int(t.id),
                        "status": str(t.status),
                        "user_id": int(t.user_id),
                        "subject": str(t.subject or ""),
                        "created_at": t.created_at.isoformat() if getattr(t, "created_at", None) else None,
                    }
                )
            return out

    async def set_active_ticket(self, *, user_id: int, ticket_id: int) -> None:
        now = datetime.utcnow()
        async with db.session() as session:
            state = await session.get(TicketUserState, int(user_id))
            if not state:
                state = TicketUserState(user_id=int(user_id), ticket_id=int(ticket_id), updated_at=now)
                session.add(state)
                return
            state.ticket_id = int(ticket_id)
            state.updated_at = now

    async def clear_active_ticket(self, *, user_id: int) -> None:
        async with db.session() as session:
            state = await session.get(TicketUserState, int(user_id))
            if state:
                await session.delete(state)

    async def get_active_ticket(self, *, user_id: int) -> dict | None:
        """
        Return the active open ticket for this user, if any.
        """
        async with db.session() as session:
            state = await session.get(TicketUserState, int(user_id))
            if not state:
                return None
            ticket = await session.get(Ticket, int(state.ticket_id))
            if not ticket or str(getattr(ticket, "status", "")) != "open":
                await session.delete(state)
                return None
            return {
                "id": int(ticket.id),
                "group_id": int(ticket.group_id),
                "user_id": int(ticket.user_id),
                "status": str(ticket.status),
                "subject": str(ticket.subject or ""),
                "staff_chat_id": int(ticket.staff_chat_id) if getattr(ticket, "staff_chat_id", None) is not None else None,
                "staff_thread_id": int(ticket.staff_thread_id) if getattr(ticket, "staff_thread_id", None) is not None else None,
                "staff_message_id": int(ticket.staff_message_id) if getattr(ticket, "staff_message_id", None) is not None else None,
                "created_at": ticket.created_at.isoformat() if getattr(ticket, "created_at", None) else None,
            }

    async def get_ticket_by_staff_thread(self, *, staff_chat_id: int, thread_id: int) -> dict | None:
        async with db.session() as session:
            result = await session.execute(
                select(Ticket)
                .where(
                    Ticket.staff_chat_id == int(staff_chat_id),
                    Ticket.staff_thread_id == int(thread_id),
                )
                .order_by(Ticket.created_at.desc(), Ticket.id.desc())
                .limit(1)
            )
            ticket = result.scalar_one_or_none()
            if not ticket:
                return None
            return {
                "id": int(ticket.id),
                "group_id": int(ticket.group_id),
                "user_id": int(ticket.user_id),
                "status": str(ticket.status),
                "subject": str(ticket.subject or ""),
                "staff_chat_id": int(ticket.staff_chat_id) if getattr(ticket, "staff_chat_id", None) is not None else None,
                "staff_thread_id": int(ticket.staff_thread_id) if getattr(ticket, "staff_thread_id", None) is not None else None,
                "staff_message_id": int(ticket.staff_message_id) if getattr(ticket, "staff_message_id", None) is not None else None,
            }

    async def get_ticket_by_staff_message(self, *, staff_chat_id: int, staff_message_id: int) -> dict | None:
        async with db.session() as session:
            result = await session.execute(
                select(Ticket)
                .where(
                    Ticket.staff_chat_id == int(staff_chat_id),
                    Ticket.staff_message_id == int(staff_message_id),
                )
                .order_by(Ticket.created_at.desc(), Ticket.id.desc())
                .limit(1)
            )
            ticket = result.scalar_one_or_none()
            if not ticket:
                return None
            return {
                "id": int(ticket.id),
                "group_id": int(ticket.group_id),
                "user_id": int(ticket.user_id),
                "status": str(ticket.status),
                "subject": str(ticket.subject or ""),
                "staff_chat_id": int(ticket.staff_chat_id) if getattr(ticket, "staff_chat_id", None) is not None else None,
                "staff_thread_id": int(ticket.staff_thread_id) if getattr(ticket, "staff_thread_id", None) is not None else None,
                "staff_message_id": int(ticket.staff_message_id) if getattr(ticket, "staff_message_id", None) is not None else None,
            }

    async def close_ticket(
        self,
        *,
        bot: Bot,
        ticket_id: int,
        closed_by_user_id: int | None = None,
        notify_user: bool = True,
        close_topic: bool = True,
    ) -> bool:
        """
        Close a ticket and (best-effort) close the forum topic if one was created.
        """
        logger.info(f"Closing ticket #{ticket_id} (by user {closed_by_user_id})")
        now = datetime.utcnow()
        async with db.session() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if not ticket:
                logger.warning(f"Ticket #{ticket_id} not found")
                return False
            if str(getattr(ticket, "status", "")) == "closed":
                logger.info(f"Ticket #{ticket_id} already closed")
                return True
            ticket.status = "closed"
            ticket.closed_at = now

            # Clear the user's active pointer if it points at this ticket.
            try:
                state = await session.get(TicketUserState, int(ticket.user_id))
                if state and int(state.ticket_id) == int(ticket.id):
                    await session.delete(state)
            except Exception as e:
                logger.debug(f"Could not clear user state for ticket #{ticket_id}: {e}")

            staff_chat_id = int(ticket.staff_chat_id) if getattr(ticket, "staff_chat_id", None) is not None else None
            staff_thread_id = int(ticket.staff_thread_id) if getattr(ticket, "staff_thread_id", None) is not None else None
            user_id = int(ticket.user_id)

        if close_topic and staff_chat_id and staff_thread_id:
            try:
                await bot.close_forum_topic(chat_id=staff_chat_id, message_thread_id=staff_thread_id)
                logger.info(f"Closed forum topic {staff_thread_id} for ticket #{ticket_id}")
            except Exception as e:
                logger.debug(f"Could not close forum topic for ticket #{ticket_id}: {e}")

        if staff_chat_id:
            try:
                text = f"✅ Ticket <code>#{int(ticket_id)}</code> closed."
                kwargs = {"disable_web_page_preview": True}
                if staff_thread_id:
                    kwargs["message_thread_id"] = staff_thread_id
                await bot.send_message(chat_id=staff_chat_id, text=text, parse_mode="HTML", **kwargs)
            except Exception as e:
                logger.debug(f"Could not notify staff about ticket #{ticket_id} closure: {e}")

        if notify_user:
            try:
                by = f" by support" if closed_by_user_id else ""
                await bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Ticket <code>#{int(ticket_id)}</code> closed{by}.\n\nThank you for contacting support!",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.debug(f"Could not notify user about ticket #{ticket_id} closure: {e}")

        logger.info(f"Ticket #{ticket_id} closed successfully")
        return True

    async def create_ticket(
        self,
        *,
        bot: Bot,
        group_id: int,
        user_id: int,
        message: str,
        subject: Optional[str] = None,
        priority: Optional[str] = None,
        image_file_id: Optional[str] = None,
    ) -> int:
        msg = (message or "").strip()
        if not msg:
            raise ValueError("message is empty")
        if len(msg) > 2000:
            raise ValueError("message is too long")

        subject_norm = (subject or "").strip() or msg.splitlines()[0][:80]
        priority_norm = (priority or "normal").strip().lower()
        if priority_norm not in ("low", "normal", "high", "urgent"):
            priority_norm = "normal"
        
        now = datetime.utcnow()

        staff_chat_id: int
        staff_thread_id: int | None = None
        logs_thread_id: int | None = None

        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == int(group_id)))
            group = result.scalar_one_or_none()
            if not group:
                raise ValueError("group is unknown")
            if not getattr(group, "logs_enabled", False) or not getattr(group, "logs_chat_id", None):
                raise ValueError("support is not configured (logs destination is off)")

            staff_chat_id = int(group.logs_chat_id)
            logs_thread_id = int(group.logs_thread_id) if getattr(group, "logs_thread_id", None) else None

            ticket = Ticket(
                group_id=int(group_id),
                user_id=int(user_id),
                status="open",
                subject=subject_norm,
                message=msg,
                priority=priority_norm,
                created_at=now,
                closed_at=None,
                staff_chat_id=staff_chat_id,
                staff_thread_id=None,
                staff_message_id=None,
                last_message_at=now,
                last_user_message_at=now,
                message_count=1,
            )
            session.add(ticket)
            await session.flush()
            ticket_id = int(ticket.id)
            
            # Store the initial message in history
            initial_msg = TicketMessage(
                ticket_id=ticket_id,
                sender_type="user",
                sender_id=int(user_id),
                message_type="photo" if image_file_id else "text",
                content=msg,
                file_id=image_file_id,
                created_at=now,
            )
            session.add(initial_msg)

        logger.info(f"Creating ticket #{ticket_id} for user {user_id} in group {group_id}")
        
        # Try to create a dedicated forum topic (best UX for staff). If it fails, fall back to logs chat/thread.
        topic_thread_id: int | None = None
        try:
            chat = await bot.get_chat(staff_chat_id)
            if bool(getattr(chat, "is_forum", False)):
                topic_name = f"Ticket #{ticket_id} • {subject_norm}".strip()
                topic_name = topic_name[:128]
                topic = await bot.create_forum_topic(chat_id=staff_chat_id, name=topic_name)
                topic_thread_id = int(getattr(topic, "message_thread_id", 0) or 0) or None
                logger.info(f"Created forum topic {topic_thread_id} for ticket #{ticket_id}")
        except Exception as e:
            logger.warning(f"Could not create forum topic for ticket #{ticket_id}: {e}")
            topic_thread_id = None

        # Priority emoji
        priority_emoji = {"low": "🟢", "normal": "🟡", "high": "🟠", "urgent": "🔴"}.get(priority_norm, "🟡")
        
        text = (
            f"<b>{priority_emoji} Ticket #{ticket_id}</b>\n"
            f"Group: <code>{int(group_id)}</code>\n"
            f"User: <code>{int(user_id)}</code>\n"
            f"Priority: <b>{priority_norm.upper()}</b>\n"
            f"Subject: {escape(subject_norm)}\n\n"
            f"{escape(msg)}"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Close ticket", callback_data=f"tix:close:{ticket_id}")]]
        )
        kwargs = {"disable_web_page_preview": True}
        if topic_thread_id:
            kwargs["message_thread_id"] = topic_thread_id
        elif logs_thread_id:
            kwargs["message_thread_id"] = logs_thread_id

        try:
            # If there's an image, send it with the caption
            if image_file_id:
                sent = await bot.send_photo(
                    chat_id=staff_chat_id,
                    photo=image_file_id,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                    **kwargs
                )
            else:
                sent = await bot.send_message(
                    chat_id=staff_chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                    **kwargs
                )
            logger.info(f"Sent ticket #{ticket_id} to staff chat {staff_chat_id}")
        except Exception as e:
            logger.error(f"Failed to send ticket #{ticket_id} to staff chat: {e}")
            raise ValueError(f"Could not notify staff: {e}")

        async with db.session() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket:
                ticket.staff_message_id = int(getattr(sent, "message_id", 0) or 0) or None
                if topic_thread_id:
                    ticket.staff_thread_id = int(topic_thread_id)

        logger.info(f"Ticket #{ticket_id} created successfully")
        return int(ticket_id)
