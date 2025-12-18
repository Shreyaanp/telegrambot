"""Broadcast service - send announcements to multiple chats via background jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from aiogram import Bot
from aiogram.exceptions import (
    TelegramRetryAfter,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramUnauthorizedError,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, func

from database.db import db
from database.models import Broadcast, BroadcastTarget, DmSubscriber
from bot.services.jobs_service import JobsService


@dataclass(frozen=True)
class BroadcastJobResult:
    done: bool
    retry_after_seconds: int | None = None
    detail: str | None = None


class BroadcastService:
    def __init__(self, jobs: JobsService):
        self.jobs = jobs

    async def list_recent_for_group(self, *, group_id: int, limit: int = 20) -> list[dict]:
        limit = int(limit or 20)
        limit = max(1, min(limit, 50))

        async with db.session() as session:
            result = await session.execute(
                select(BroadcastTarget, Broadcast)
                .join(Broadcast, Broadcast.id == BroadcastTarget.broadcast_id)
                .where(BroadcastTarget.chat_id == int(group_id))
                .order_by(BroadcastTarget.id.desc())
                .limit(limit)
            )
            rows = list(result.all())

        out: list[dict] = []
        for target, broadcast in rows:
            text = str(getattr(broadcast, "text", "") or "")
            preview = text if len(text) <= 140 else (text[:137] + "...")
            out.append(
                {
                    "id": int(broadcast.id),
                    "status": str(getattr(broadcast, "status", "") or ""),
                    "created_by": int(getattr(broadcast, "created_by", 0) or 0),
                    "created_at": getattr(broadcast, "created_at", None).isoformat()
                    if getattr(broadcast, "created_at", None)
                    else None,
                    "scheduled_at": getattr(broadcast, "scheduled_at", None).isoformat()
                    if getattr(broadcast, "scheduled_at", None)
                    else None,
                    "started_at": getattr(broadcast, "started_at", None).isoformat()
                    if getattr(broadcast, "started_at", None)
                    else None,
                    "finished_at": getattr(broadcast, "finished_at", None).isoformat()
                    if getattr(broadcast, "finished_at", None)
                    else None,
                    "total_targets": int(getattr(broadcast, "total_targets", 0) or 0),
                    "sent_count": int(getattr(broadcast, "sent_count", 0) or 0),
                    "failed_count": int(getattr(broadcast, "failed_count", 0) or 0),
                    "last_error": str(getattr(broadcast, "last_error", "") or "") or None,
                    "text_preview": preview,
                    "target_status": str(getattr(target, "status", "") or ""),
                    "target_sent_at": getattr(target, "sent_at", None).isoformat()
                    if getattr(target, "sent_at", None)
                    else None,
                    "target_error": str(getattr(target, "error", "") or "") or None,
                }
            )
        return out

    async def create_group_broadcast(
        self,
        *,
        created_by: int,
        chat_ids: Iterable[int],
        text: str,
        delay_seconds: int = 0,
        parse_mode: str | None = "Markdown",
        disable_web_page_preview: bool = True,
    ) -> int:
        """
        Create a group broadcast and enqueue a send job.
        """
        deduped: list[int] = []
        seen: set[int] = set()
        for cid in chat_ids:
            try:
                chat_id = int(cid)
            except Exception:
                continue
            if chat_id in seen:
                continue
            seen.add(chat_id)
            deduped.append(chat_id)

        if not text or not text.strip():
            raise ValueError("broadcast text is empty")
        if not deduped:
            raise ValueError("no targets selected")

        now = datetime.utcnow()
        delay_seconds = int(delay_seconds or 0)
        delay_seconds = max(0, min(delay_seconds, 7 * 24 * 3600))
        run_at = now + timedelta(seconds=delay_seconds)
        broadcast = Broadcast(
            created_by=int(created_by),
            created_at=now,
            scheduled_at=run_at,
            status="pending",
            started_at=None,
            finished_at=None,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=bool(disable_web_page_preview),
            total_targets=len(deduped),
            sent_count=0,
            failed_count=0,
            last_error=None,
        )

        async with db.session() as session:
            session.add(broadcast)
            await session.flush()
            bid = int(broadcast.id)

            for chat_id in deduped:
                session.add(
                    BroadcastTarget(
                        broadcast_id=bid,
                        chat_id=int(chat_id),
                        status="pending",
                        telegram_message_id=None,
                        sent_at=None,
                        error=None,
                        created_at=now,
                    )
                )

        await self.jobs.enqueue("broadcast_send", {"broadcast_id": bid}, run_at=run_at)
        return bid

    async def create_dm_broadcast(
        self,
        *,
        created_by: int,
        text: str,
        delay_seconds: int = 0,
        parse_mode: str | None = "Markdown",
        disable_web_page_preview: bool = True,
        max_targets: int = 5000,
    ) -> tuple[int, int]:
        """
        Create a DM broadcast to all deliverable DM subscribers (not opted out).

        Returns:
            (broadcast_id, total_targets)
        """
        if not text or not text.strip():
            raise ValueError("broadcast text is empty")
        if len(text) > 4096:
            raise ValueError("broadcast text is too long")

        max_targets = max(1, min(int(max_targets or 5000), 20000))

        now = datetime.utcnow()
        delay_seconds = int(delay_seconds or 0)
        delay_seconds = max(0, min(delay_seconds, 7 * 24 * 3600))
        run_at = now + timedelta(seconds=delay_seconds)

        async with db.session() as session:
            subs_result = await session.execute(
                select(DmSubscriber.telegram_id)
                .where(DmSubscriber.deliverable.is_(True), DmSubscriber.opted_out.is_(False))
                .order_by(DmSubscriber.last_seen_at.desc())
                .limit(max_targets)
            )
            user_ids = [int(r[0]) for r in subs_result.all() if r and r[0] is not None]

            if not user_ids:
                raise ValueError("no DM subscribers yet")

            broadcast = Broadcast(
                created_by=int(created_by),
                created_at=now,
                scheduled_at=run_at,
                status="pending",
                started_at=None,
                finished_at=None,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=bool(disable_web_page_preview),
                total_targets=len(user_ids),
                sent_count=0,
                failed_count=0,
                last_error=None,
            )
            session.add(broadcast)
            await session.flush()
            bid = int(broadcast.id)

            for uid in user_ids:
                session.add(
                    BroadcastTarget(
                        broadcast_id=bid,
                        chat_id=int(uid),
                        status="pending",
                        telegram_message_id=None,
                        sent_at=None,
                        error=None,
                        created_at=now,
                    )
                )

        await self.jobs.enqueue("broadcast_send", {"broadcast_id": bid}, run_at=run_at)
        return bid, len(user_ids)

    async def run_send_job(self, bot: Bot, *, broadcast_id: int, batch_size: int = 5) -> BroadcastJobResult:
        """
        Send up to `batch_size` pending targets for a broadcast.

        This is designed to be called from a job worker; it is idempotent per target status.
        """
        now = datetime.utcnow()

        async with db.session() as session:
            result = await session.execute(select(Broadcast).where(Broadcast.id == int(broadcast_id)))
            broadcast = result.scalar_one_or_none()
            if not broadcast:
                return BroadcastJobResult(done=True, detail="broadcast missing")

            if broadcast.status in ("completed", "cancelled", "failed"):
                return BroadcastJobResult(done=True, detail=f"broadcast status={broadcast.status}")

            if broadcast.status == "pending":
                broadcast.status = "running"
                broadcast.started_at = now

            result = await session.execute(
                select(BroadcastTarget)
                .where(BroadcastTarget.broadcast_id == int(broadcast_id), BroadcastTarget.status == "pending")
                .order_by(BroadcastTarget.id.asc())
                .limit(int(batch_size))
                .with_for_update(skip_locked=True)
            )
            targets = list(result.scalars().all())

            if not targets:
                broadcast.status = "completed"
                broadcast.finished_at = now
                return BroadcastJobResult(done=True, detail="no pending targets")

            for target in targets:
                is_dm = int(target.chat_id) > 0
                try:
                    reply_markup = None
                    if is_dm:
                        reply_markup = InlineKeyboardMarkup(
                            inline_keyboard=[[InlineKeyboardButton(text="Unsubscribe", callback_data="dm:unsub")]]
                        )
                    msg = await bot.send_message(
                        chat_id=int(target.chat_id),
                        text=str(broadcast.text),
                        parse_mode=(str(broadcast.parse_mode) if broadcast.parse_mode else None),
                        disable_web_page_preview=bool(getattr(broadcast, "disable_web_page_preview", True)),
                        reply_markup=reply_markup,
                    )
                    target.status = "sent"
                    target.telegram_message_id = int(getattr(msg, "message_id", 0) or 0) or None
                    target.sent_at = now
                    broadcast.sent_count = int(broadcast.sent_count or 0) + 1
                    if is_dm:
                        sub = await session.get(DmSubscriber, int(target.chat_id))
                        if sub:
                            sub.deliverable = True
                            sub.last_ok_at = now
                            sub.last_error = None
                            sub.fail_count = 0
                except TelegramRetryAfter as e:
                    broadcast.last_error = f"retry_after={int(e.retry_after)}"
                    return BroadcastJobResult(
                        done=False,
                        retry_after_seconds=int(e.retry_after),
                        detail="telegram rate limit",
                    )
                except Exception as e:
                    target.status = "failed"
                    target.error = str(e)[:2000]
                    target.sent_at = now
                    broadcast.failed_count = int(broadcast.failed_count or 0) + 1
                    if is_dm:
                        sub = await session.get(DmSubscriber, int(target.chat_id))
                        if sub:
                            sub.last_fail_at = now
                            sub.last_error = str(e)[:2000]
                            sub.fail_count = int(getattr(sub, "fail_count", 0) or 0) + 1
                            if isinstance(e, (TelegramForbiddenError, TelegramNotFound, TelegramUnauthorizedError)):
                                sub.deliverable = False

            # Decide if we have more work.
            pending_count_result = await session.execute(
                select(func.count())
                .select_from(BroadcastTarget)
                .where(BroadcastTarget.broadcast_id == int(broadcast_id), BroadcastTarget.status == "pending")
            )
            pending_count = int(pending_count_result.scalar() or 0)
            if pending_count <= 0:
                broadcast.status = "completed"
                broadcast.finished_at = now
                return BroadcastJobResult(done=True, detail="completed")

            return BroadcastJobResult(done=False, detail=f"pending={pending_count}")
