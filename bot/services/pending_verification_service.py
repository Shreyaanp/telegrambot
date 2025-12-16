"""Pending join verification service - robust join prompts with timeouts and overrides."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot
from sqlalchemy import select, and_

from database.db import db
from database.models import PendingJoinVerification, GroupUserState

logger = logging.getLogger(__name__)


class PendingVerificationService:
    """DB-backed pending join verification records and expiry processing."""

    async def touch_group_user(self, group_id: int, telegram_id: int):
        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(
                select(GroupUserState).where(
                    GroupUserState.group_id == group_id,
                    GroupUserState.telegram_id == telegram_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                session.add(GroupUserState(group_id=group_id, telegram_id=telegram_id, first_seen_at=now, last_seen_at=now, join_count=1))
            else:
                row.last_seen_at = now
                row.join_count = int(row.join_count or 0) + 1

    async def mark_group_user_verified(self, group_id: int, telegram_id: int, mercle_session_id: Optional[str] = None):
        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(
                select(GroupUserState).where(
                    GroupUserState.group_id == group_id,
                    GroupUserState.telegram_id == telegram_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                session.add(
                    GroupUserState(
                        group_id=group_id,
                        telegram_id=telegram_id,
                        first_seen_at=now,
                        last_seen_at=now,
                        join_count=1,
                        first_verified_seen_at=now,
                        last_verification_session_id=mercle_session_id,
                    )
                )
            else:
                if row.first_verified_seen_at is None:
                    row.first_verified_seen_at = now
                row.last_seen_at = now
                row.last_verification_session_id = mercle_session_id or row.last_verification_session_id

    async def create_pending(self, group_id: int, telegram_id: int, expires_at: datetime) -> PendingJoinVerification:
        async with db.session() as session:
            row = PendingJoinVerification(group_id=group_id, telegram_id=telegram_id, expires_at=expires_at, status="pending")
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return row

    async def set_prompt_message_id(self, pending_id: int, message_id: int):
        async with db.session() as session:
            result = await session.execute(select(PendingJoinVerification).where(PendingJoinVerification.id == pending_id))
            row = result.scalar_one_or_none()
            if row:
                row.prompt_message_id = message_id

    async def set_dm_message_id(self, pending_id: int, message_id: int):
        async with db.session() as session:
            result = await session.execute(select(PendingJoinVerification).where(PendingJoinVerification.id == pending_id))
            row = result.scalar_one_or_none()
            if row:
                row.dm_message_id = message_id

    async def attach_session(self, pending_id: int, session_id: str):
        async with db.session() as session:
            result = await session.execute(select(PendingJoinVerification).where(PendingJoinVerification.id == pending_id))
            row = result.scalar_one_or_none()
            if row:
                row.mercle_session_id = session_id

    async def get_pending(self, pending_id: int) -> Optional[PendingJoinVerification]:
        async with db.session() as session:
            result = await session.execute(select(PendingJoinVerification).where(PendingJoinVerification.id == pending_id))
            return result.scalar_one_or_none()

    async def get_active_for_user(self, group_id: int, telegram_id: int) -> Optional[PendingJoinVerification]:
        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(
                select(PendingJoinVerification)
                .where(
                    and_(
                        PendingJoinVerification.group_id == group_id,
                        PendingJoinVerification.telegram_id == telegram_id,
                        PendingJoinVerification.status == "pending",
                        PendingJoinVerification.expires_at > now,
                    )
                )
                .order_by(PendingJoinVerification.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def decide(self, pending_id: int, status: str, decided_by: int):
        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(select(PendingJoinVerification).where(PendingJoinVerification.id == pending_id))
            row = result.scalar_one_or_none()
            if not row or row.status != "pending":
                return
            row.status = status
            row.decided_by = decided_by
            row.decided_at = now

    async def find_expired(self) -> list[PendingJoinVerification]:
        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(
                select(PendingJoinVerification)
                .where(
                    and_(
                        PendingJoinVerification.status == "pending",
                        PendingJoinVerification.expires_at <= now,
                    )
                )
            )
            return list(result.scalars().all())

    async def edit_or_delete_group_prompt(self, bot: Bot, pending: PendingJoinVerification, text: str, delete_after_seconds: int = 600):
        if not pending.prompt_message_id:
            return
        try:
            await bot.edit_message_text(
                chat_id=int(pending.group_id),
                message_id=int(pending.prompt_message_id),
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            return
        if delete_after_seconds <= 0:
            return
        try:
            import asyncio

            async def _del():
                await asyncio.sleep(delete_after_seconds)
                try:
                    await bot.delete_message(chat_id=int(pending.group_id), message_id=int(pending.prompt_message_id))
                except Exception:
                    pass

            asyncio.create_task(_del())
        except Exception:
            pass

    async def delete_group_prompt(self, bot: Bot, pending: PendingJoinVerification):
        if not pending.prompt_message_id:
            return
        try:
            await bot.delete_message(chat_id=int(pending.group_id), message_id=int(pending.prompt_message_id))
        except Exception:
            pass
