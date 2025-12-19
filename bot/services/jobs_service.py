"""Jobs service - small DB-backed job queue for background work."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update, func

from database.db import db
from database.models import Job


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    job_type: str
    payload: dict[str, Any]
    attempts: int


class JobsService:
    async def enqueue(self, job_type: str, payload: dict[str, Any], *, run_at: datetime | None = None) -> int:
        job = Job(
            job_type=str(job_type),
            status="pending",
            run_at=run_at or datetime.utcnow(),
            attempts=0,
            locked_at=None,
            locked_by=None,
            payload=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            last_error=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        async with db.session() as session:
            session.add(job)
            await session.flush()
            return int(job.id)

    async def release_stale_locks(self, *, max_age_seconds: int = 600) -> int:
        """
        Release jobs stuck in `running` state (e.g. after a crash/restart).
        """
        cutoff = datetime.utcnow() - timedelta(seconds=int(max_age_seconds))
        async with db.session() as session:
            result = await session.execute(
                update(Job)
                .where(Job.status == "running", Job.locked_at.is_not(None), Job.locked_at < cutoff)
                .values(status="pending", locked_at=None, locked_by=None, updated_at=datetime.utcnow())
            )
            return int(result.rowcount or 0)

    async def claim_due(self, *, limit: int = 5, lock_for_seconds: int = 300) -> list[ClaimedJob]:
        """
        Claim due jobs using row locks (FOR UPDATE SKIP LOCKED).
        """
        now = datetime.utcnow()
        locked_by = f"pid:{os.getpid()}"

        async with db.session() as session:
            result = await session.execute(
                select(Job)
                .where(Job.status == "pending", Job.run_at <= now)
                .order_by(Job.run_at.asc(), Job.id.asc())
                .limit(int(limit))
                .with_for_update(skip_locked=True)
            )
            jobs = list(result.scalars().all())
            claimed: list[ClaimedJob] = []
            for job in jobs:
                job.status = "running"
                job.attempts = int(getattr(job, "attempts", 0) or 0) + 1
                job.locked_at = now
                job.locked_by = locked_by
                job.updated_at = now

                raw_payload = getattr(job, "payload", "") or "{}"
                try:
                    payload = json.loads(raw_payload)
                except Exception:
                    payload = {}
                claimed.append(
                    ClaimedJob(
                        id=int(job.id),
                        job_type=str(job.job_type),
                        payload=payload if isinstance(payload, dict) else {},
                        attempts=int(job.attempts),
                    )
                )

            return claimed

    async def reschedule(
        self,
        job_id: int,
        *,
        run_at: datetime,
        last_error: str | None = None,
        payload_patch: dict[str, Any] | None = None,
    ) -> None:
        async with db.session() as session:
            job = await session.get(Job, int(job_id))
            if not job:
                return
            job.status = "pending"
            job.run_at = run_at
            job.locked_at = None
            job.locked_by = None
            if last_error is not None:
                job.last_error = last_error[:4000]
            if payload_patch:
                raw = getattr(job, "payload", "") or "{}"
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                data.update(payload_patch)
                job.payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
            job.updated_at = datetime.utcnow()

    async def mark_done(self, job_id: int) -> None:
        async with db.session() as session:
            job = await session.get(Job, int(job_id))
            if not job:
                return
            job.status = "done"
            job.locked_at = None
            job.locked_by = None
            job.updated_at = datetime.utcnow()

    async def mark_failed(self, job_id: int, *, last_error: str) -> None:
        async with db.session() as session:
            job = await session.get(Job, int(job_id))
            if not job:
                return
            job.status = "failed"
            job.locked_at = None
            job.locked_by = None
            job.last_error = (last_error or "")[:4000]
            job.updated_at = datetime.utcnow()

    async def count_pending(self) -> int:
        async with db.session() as session:
            result = await session.execute(select(func.count()).select_from(Job).where(Job.status == "pending"))
            return int(result.scalar() or 0)
