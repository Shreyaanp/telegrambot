"""Ticket service - create simple support tickets and notify staff via logs destination."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Optional

from aiogram import Bot
from sqlalchemy import select

from database.db import db
from database.models import Group, Ticket


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

        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == int(group_id)))
            group = result.scalar_one_or_none()
            if not group:
                raise ValueError("group is unknown")
            if not getattr(group, "logs_enabled", False) or not getattr(group, "logs_chat_id", None):
                raise ValueError("support is not configured (logs destination is off)")

            staff_chat_id = int(group.logs_chat_id)
            staff_thread_id = int(group.logs_thread_id) if getattr(group, "logs_thread_id", None) else None

            ticket = Ticket(
                group_id=int(group_id),
                user_id=int(user_id),
                status="open",
                subject=subject_norm,
                message=msg,
                created_at=now,
                closed_at=None,
                staff_chat_id=staff_chat_id,
                staff_thread_id=staff_thread_id,
                staff_message_id=None,
            )
            session.add(ticket)
            await session.flush()

            text = (
                f"<b>Ticket #{int(ticket.id)}</b>\n"
                f"Group: <code>{int(group_id)}</code>\n"
                f"User: <code>{int(user_id)}</code>\n"
                f"Subject: {escape(subject_norm)}\n\n"
                f"{escape(msg)}"
            )
            kwargs = {"disable_web_page_preview": True}
            if staff_thread_id:
                kwargs["message_thread_id"] = staff_thread_id
            sent = await bot.send_message(chat_id=staff_chat_id, text=text, parse_mode="HTML", **kwargs)
            ticket.staff_message_id = int(getattr(sent, "message_id", 0) or 0) or None

            return int(ticket.id)
