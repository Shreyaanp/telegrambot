"""Ticket service - support tickets (v1 + forum-topic bridge v2)."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from database.db import db
from database.models import Group, Ticket, TicketUserState


class TicketService:
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
        now = datetime.utcnow()
        async with db.session() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if not ticket:
                return False
            if str(getattr(ticket, "status", "")) == "closed":
                return True
            ticket.status = "closed"
            ticket.closed_at = now

            # Clear the user's active pointer if it points at this ticket.
            try:
                state = await session.get(TicketUserState, int(ticket.user_id))
                if state and int(state.ticket_id) == int(ticket.id):
                    await session.delete(state)
            except Exception:
                pass

            staff_chat_id = int(ticket.staff_chat_id) if getattr(ticket, "staff_chat_id", None) is not None else None
            staff_thread_id = int(ticket.staff_thread_id) if getattr(ticket, "staff_thread_id", None) is not None else None
            user_id = int(ticket.user_id)

        if close_topic and staff_chat_id and staff_thread_id:
            try:
                await bot.close_forum_topic(chat_id=staff_chat_id, message_thread_id=staff_thread_id)
            except Exception:
                pass

        if staff_chat_id:
            try:
                text = f"✅ Ticket <code>#{int(ticket_id)}</code> closed."
                kwargs = {"disable_web_page_preview": True}
                if staff_thread_id:
                    kwargs["message_thread_id"] = staff_thread_id
                await bot.send_message(chat_id=staff_chat_id, text=text, parse_mode="HTML", **kwargs)
            except Exception:
                pass

        if notify_user:
            try:
                by = f" by <code>{int(closed_by_user_id)}</code>" if closed_by_user_id else ""
                await bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Ticket <code>#{int(ticket_id)}</code> closed{by}.",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        return True

    async def create_ticket(
        self,
        *,
        bot: Bot,
        group_id: int,
        user_id: int,
        message: str,
        subject: Optional[str] = None,
    ) -> int:
        msg = (message or "").strip()
        if not msg:
            raise ValueError("message is empty")
        if len(msg) > 2000:
            raise ValueError("message is too long")

        subject_norm = (subject or "").strip() or msg.splitlines()[0][:80]
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
                created_at=now,
                closed_at=None,
                staff_chat_id=staff_chat_id,
                staff_thread_id=None,
                staff_message_id=None,
            )
            session.add(ticket)
            await session.flush()
            ticket_id = int(ticket.id)

        # Try to create a dedicated forum topic (best UX for staff). If it fails, fall back to logs chat/thread.
        topic_thread_id: int | None = None
        try:
            chat = await bot.get_chat(staff_chat_id)
            if bool(getattr(chat, "is_forum", False)):
                topic_name = f"Ticket #{ticket_id} • {subject_norm}".strip()
                topic_name = topic_name[:128]
                topic = await bot.create_forum_topic(chat_id=staff_chat_id, name=topic_name)
                topic_thread_id = int(getattr(topic, "message_thread_id", 0) or 0) or None
        except Exception:
            topic_thread_id = None

        text = (
            f"<b>Ticket #{ticket_id}</b>\n"
            f"Group: <code>{int(group_id)}</code>\n"
            f"User: <code>{int(user_id)}</code>\n"
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

        sent = await bot.send_message(chat_id=staff_chat_id, text=text, parse_mode="HTML", reply_markup=kb, **kwargs)

        async with db.session() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket:
                ticket.staff_message_id = int(getattr(sent, "message_id", 0) or 0) or None
                if topic_thread_id:
                    ticket.staff_thread_id = int(topic_thread_id)

        return int(ticket_id)
