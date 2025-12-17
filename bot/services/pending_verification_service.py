"""Pending join verification service - robust join prompts with timeouts and overrides."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError

from database.db import db
from database.models import PendingJoinVerification, GroupUserState

logger = logging.getLogger(__name__)

_STARTING_SENTINEL = "starting"


class PendingVerificationService:
    """DB-backed pending join verification records and expiry processing."""

    async def _safe_remove_prompt(self, bot: Bot, pending: PendingJoinVerification, *, fallback_text: str | None = None) -> None:
        if not pending.prompt_message_id:
            return
        chat_id = int(pending.group_id)
        message_id = int(pending.prompt_message_id)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            return
        except Exception:
            pass
        # Fallback for older messages / insufficient rights: remove buttons and optionally edit text.
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        except Exception:
            pass
        if fallback_text:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=fallback_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception:
                pass

    async def touch_group_user(
        self,
        group_id: int,
        telegram_id: int,
        *,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        source: Optional[str] = None,
        increment_join: bool = False,
    ):
        now = datetime.utcnow()
        username_norm = (username or "").lstrip("@").strip()
        username_lc = username_norm.lower() if username_norm else None
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
                        username=username_norm or None,
                        username_lc=username_lc,
                        first_name=first_name,
                        last_name=last_name,
                        last_source=source,
                        first_seen_at=now,
                        last_seen_at=now,
                        join_count=1 if increment_join else 0,
                    )
                )
            else:
                row.last_seen_at = now
                if username_lc:
                    row.username = username_norm
                    row.username_lc = username_lc
                if first_name is not None:
                    row.first_name = first_name
                if last_name is not None:
                    row.last_name = last_name
                if source:
                    row.last_source = source
                if increment_join:
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

    async def get_active_for_user(self, group_id: int, telegram_id: int, *, kind: Optional[str] = None) -> Optional[PendingJoinVerification]:
        now = datetime.utcnow()
        async with db.session() as session:
            cond = [
                PendingJoinVerification.group_id == group_id,
                PendingJoinVerification.telegram_id == telegram_id,
                PendingJoinVerification.status == "pending",
                PendingJoinVerification.expires_at > now,
            ]
            if kind:
                cond.append(PendingJoinVerification.kind == kind)
            result = await session.execute(
                select(PendingJoinVerification)
                .where(
                    and_(
                        *cond
                    )
                )
                .order_by(PendingJoinVerification.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def create_pending(
        self,
        *,
        group_id: int,
        telegram_id: int,
        expires_at: datetime,
        kind: str = "post_join",
        user_chat_id: Optional[int] = None,
        join_request_at: Optional[datetime] = None,
    ) -> PendingJoinVerification:
        """
        Create a pending verification row, enforcing "one active pending" per (group_id, telegram_id, kind).

        With the partial unique index `uq_pv_active`, concurrent creates will raise IntegrityError; in that case
        we return the existing active pending.
        """
        now = datetime.utcnow()
        async with db.session() as session:
            existing = await session.execute(
                select(PendingJoinVerification)
                .where(
                    and_(
                        PendingJoinVerification.group_id == group_id,
                        PendingJoinVerification.telegram_id == telegram_id,
                        PendingJoinVerification.kind == kind,
                        PendingJoinVerification.status == "pending",
                        PendingJoinVerification.expires_at > now,
                    )
                )
                .order_by(PendingJoinVerification.created_at.desc())
                .limit(1)
            )
            row = existing.scalar_one_or_none()
            if row:
                if user_chat_id is not None and getattr(row, "user_chat_id", None) is None:
                    row.user_chat_id = user_chat_id
                if join_request_at is not None and getattr(row, "join_request_at", None) is None:
                    row.join_request_at = join_request_at
                if expires_at and row.expires_at < expires_at:
                    row.expires_at = expires_at
                await session.flush()
                return row

            row = PendingJoinVerification(
                group_id=group_id,
                telegram_id=telegram_id,
                expires_at=expires_at,
                status="pending",
                kind=kind,
                user_chat_id=user_chat_id,
                join_request_at=join_request_at,
            )
            session.add(row)
            try:
                await session.flush()
            except IntegrityError:
                # Another writer created the active pending first; re-read and return it.
                await session.rollback()
                result = await session.execute(
                    select(PendingJoinVerification)
                    .where(
                        and_(
                            PendingJoinVerification.group_id == group_id,
                            PendingJoinVerification.telegram_id == telegram_id,
                            PendingJoinVerification.kind == kind,
                            PendingJoinVerification.status == "pending",
                            PendingJoinVerification.expires_at > now,
                        )
                    )
                    .order_by(PendingJoinVerification.created_at.desc())
                    .limit(1)
                )
                existing_row = result.scalar_one_or_none()
                if existing_row:
                    return existing_row
                raise
            await session.refresh(row)
            return row

    async def try_mark_starting(self, pending_id: int, telegram_id: int) -> bool:
        """
        Atomically claim a pending verification so Confirm double-taps can't start multiple Mercle sessions.

        Returns True if we successfully claimed it; False if it's already terminal or already started.
        """
        async with db.session() as session:
            result = await session.execute(
                select(PendingJoinVerification).where(PendingJoinVerification.id == pending_id)
            )
            row = result.scalar_one_or_none()
            if (
                not row
                or int(row.telegram_id) != int(telegram_id)
                or row.status != "pending"
                or row.expires_at < datetime.utcnow()
            ):
                return False
            if getattr(row, "mercle_session_id", None) not in (None, "", _STARTING_SENTINEL):
                return False
            if getattr(row, "mercle_session_id", None) == _STARTING_SENTINEL:
                return False
            row.mercle_session_id = _STARTING_SENTINEL
            return True

    async def clear_starting_if_needed(self, pending_id: int, telegram_id: int) -> None:
        """Best-effort rollback if Mercle session creation fails after we claimed 'starting'."""
        async with db.session() as session:
            result = await session.execute(
                select(PendingJoinVerification).where(PendingJoinVerification.id == pending_id)
            )
            row = result.scalar_one_or_none()
            if (
                row
                and int(row.telegram_id) == int(telegram_id)
                and row.status == "pending"
                and getattr(row, "mercle_session_id", None) == _STARTING_SENTINEL
            ):
                row.mercle_session_id = None

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
                await self._safe_remove_prompt(bot, pending)

            asyncio.create_task(_del())
        except Exception:
            pass

    async def delete_group_prompt(self, bot: Bot, pending: PendingJoinVerification):
        await self._safe_remove_prompt(bot, pending, fallback_text="✅ Resolved.")
