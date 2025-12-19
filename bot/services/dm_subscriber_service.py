"""DM subscriber service - track who can receive bot DMs (deliverability + opt-out)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, func

from database.db import db
from database.models import DmSubscriber


class DmSubscriberService:
    async def touch(
        self,
        *,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> None:
        """
        Record a DM interaction from this user (best-effort). This implies the user can talk to the bot.
        """
        now = datetime.utcnow()
        async with db.session() as session:
            sub = await session.get(DmSubscriber, int(telegram_id))
            if not sub:
                sub = DmSubscriber(
                    telegram_id=int(telegram_id),
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    opted_out=False,
                    deliverable=True,
                    fail_count=0,
                    last_error=None,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_ok_at=None,
                    last_fail_at=None,
                )
                session.add(sub)
                return

            if username is not None:
                sub.username = username
            if first_name is not None:
                sub.first_name = first_name
            if last_name is not None:
                sub.last_name = last_name
            sub.last_seen_at = now
            sub.deliverable = True
            sub.last_error = None

    async def set_opt_out(self, *, telegram_id: int, opted_out: bool) -> None:
        now = datetime.utcnow()
        async with db.session() as session:
            sub = await session.get(DmSubscriber, int(telegram_id))
            if not sub:
                sub = DmSubscriber(
                    telegram_id=int(telegram_id),
                    username=None,
                    first_name=None,
                    last_name=None,
                    opted_out=bool(opted_out),
                    deliverable=True,
                    fail_count=0,
                    last_error=None,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_ok_at=None,
                    last_fail_at=None,
                )
                session.add(sub)
                return

            sub.opted_out = bool(opted_out)
            sub.last_seen_at = now

    async def mark_send_success(self, *, telegram_id: int) -> None:
        now = datetime.utcnow()
        async with db.session() as session:
            sub = await session.get(DmSubscriber, int(telegram_id))
            if not sub:
                sub = DmSubscriber(
                    telegram_id=int(telegram_id),
                    username=None,
                    first_name=None,
                    last_name=None,
                    opted_out=False,
                    deliverable=True,
                    fail_count=0,
                    last_error=None,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_ok_at=now,
                    last_fail_at=None,
                )
                session.add(sub)
                return

            sub.deliverable = True
            sub.last_ok_at = now
            sub.last_error = None
            sub.fail_count = 0

    async def mark_send_failure(self, *, telegram_id: int, error: str, undeliverable: bool) -> None:
        now = datetime.utcnow()
        err = (error or "").strip()[:2000] or None

        async with db.session() as session:
            sub = await session.get(DmSubscriber, int(telegram_id))
            if not sub:
                sub = DmSubscriber(
                    telegram_id=int(telegram_id),
                    username=None,
                    first_name=None,
                    last_name=None,
                    opted_out=False,
                    deliverable=(not bool(undeliverable)),
                    fail_count=1,
                    last_error=err,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_ok_at=None,
                    last_fail_at=now,
                )
                session.add(sub)
                return

            sub.last_fail_at = now
            sub.last_error = err
            sub.fail_count = int(getattr(sub, "fail_count", 0) or 0) + 1
            if undeliverable:
                sub.deliverable = False

    async def list_deliverable_ids(self, *, limit: int = 5000) -> list[int]:
        limit = max(1, min(int(limit or 5000), 20000))
        async with db.session() as session:
            result = await session.execute(
                select(DmSubscriber.telegram_id)
                .where(DmSubscriber.deliverable.is_(True), DmSubscriber.opted_out.is_(False))
                .order_by(DmSubscriber.last_seen_at.desc())
                .limit(limit)
            )
            return [int(r[0]) for r in result.all() if r and r[0] is not None]

    async def count_deliverable(self) -> int:
        async with db.session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(DmSubscriber)
                .where(DmSubscriber.deliverable.is_(True), DmSubscriber.opted_out.is_(False))
            )
            return int(result.scalar() or 0)

