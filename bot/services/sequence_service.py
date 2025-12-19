"""Sequence service - drip/onboarding messages triggered by events (jobs-backed)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from database.db import db
from database.models import Sequence, SequenceStep, SequenceRun, SequenceRunStep
from bot.services.jobs_service import JobsService


@dataclass(frozen=True)
class SequenceJobResult:
    done: bool
    retry_after_seconds: int | None = None
    detail: str | None = None


class SequenceService:
    """
    Minimal sequences implementation:
    - sequences are per-group
    - first built-in is `key="onboarding_verified"` triggered by `trigger="user_verified"`
    """

    def __init__(self, jobs: JobsService):
        self.jobs = jobs

    async def get_onboarding_sequence(self, group_id: int) -> dict:
        async with db.session() as session:
            result = await session.execute(
                select(Sequence).where(Sequence.group_id == int(group_id), Sequence.key == "onboarding_verified")
            )
            seq = result.scalar_one_or_none()
            if not seq:
                return {"enabled": False, "delay_seconds": 0, "text": "", "parse_mode": "Markdown"}

            step_result = await session.execute(
                select(SequenceStep)
                .where(SequenceStep.sequence_id == int(seq.id), SequenceStep.step_order == 1)
                .limit(1)
            )
            step = step_result.scalar_one_or_none()
            if not step:
                return {"enabled": bool(getattr(seq, "enabled", False)), "delay_seconds": 0, "text": "", "parse_mode": "Markdown"}

            text = str(getattr(step, "text", "") or "")
            text = text if text.strip() else ""
            parse_mode = getattr(step, "parse_mode", None)
            if parse_mode not in ("Markdown", "HTML"):
                parse_mode = None
            return {
                "enabled": bool(getattr(seq, "enabled", False)),
                "delay_seconds": int(getattr(step, "delay_seconds", 0) or 0),
                "text": text,
                "parse_mode": parse_mode,
            }

    async def upsert_onboarding_sequence(
        self,
        *,
        group_id: int,
        admin_id: int,
        enabled: bool,
        delay_seconds: int,
        text: str,
        parse_mode: str | None = "Markdown",
    ) -> dict:
        delay_seconds = int(delay_seconds or 0)
        delay_seconds = max(0, min(delay_seconds, 7 * 24 * 3600))

        parse_mode_norm: str | None
        if parse_mode is None or parse_mode == "":
            parse_mode_norm = None
        elif parse_mode in ("Markdown", "HTML"):
            parse_mode_norm = str(parse_mode)
        else:
            raise ValueError("parse_mode must be Markdown|HTML|null")

        text = (text or "").strip()
        if enabled and not text:
            raise ValueError("onboarding text is empty")
        if len(text) > 4096:
            raise ValueError("onboarding text is too long")

        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(
                select(Sequence).where(Sequence.group_id == int(group_id), Sequence.key == "onboarding_verified")
            )
            seq = result.scalar_one_or_none()
            if not seq:
                seq = Sequence(
                    group_id=int(group_id),
                    key="onboarding_verified",
                    name="Onboarding after verification",
                    trigger="user_verified",
                    enabled=bool(enabled),
                    created_by=int(admin_id),
                    created_at=now,
                    updated_at=now,
                )
                session.add(seq)
                await session.flush()
            else:
                seq.enabled = bool(enabled)
                seq.updated_at = now

            step_result = await session.execute(
                select(SequenceStep).where(SequenceStep.sequence_id == int(seq.id), SequenceStep.step_order == 1)
            )
            step = step_result.scalar_one_or_none()
            if not step:
                step = SequenceStep(
                    sequence_id=int(seq.id),
                    step_order=1,
                    delay_seconds=int(delay_seconds),
                    text=text or " ",
                    parse_mode=parse_mode_norm,
                    disable_web_page_preview=True,
                    created_at=now,
                )
                session.add(step)
            else:
                step.delay_seconds = int(delay_seconds)
                step.text = text or " "
                step.parse_mode = parse_mode_norm
                step.disable_web_page_preview = True

        return await self.get_onboarding_sequence(int(group_id))

    async def get_onboarding_sequence_steps(self, group_id: int) -> dict:
        """
        Return onboarding sequence enabled flag + all non-empty steps.
        """
        async with db.session() as session:
            result = await session.execute(
                select(Sequence).where(Sequence.group_id == int(group_id), Sequence.key == "onboarding_verified")
            )
            seq = result.scalar_one_or_none()
            if not seq:
                return {"enabled": False, "steps": []}

            steps_result = await session.execute(
                select(SequenceStep)
                .where(SequenceStep.sequence_id == int(seq.id))
                .order_by(SequenceStep.step_order.asc())
            )
            steps_out: list[dict] = []
            for step in steps_result.scalars().all():
                text = str(getattr(step, "text", "") or "")
                if not text.strip():
                    continue
                steps_out.append(
                    {
                        "step_order": int(getattr(step, "step_order", 0) or 0),
                        "delay_seconds": int(getattr(step, "delay_seconds", 0) or 0),
                        "text": text,
                        "parse_mode": str(getattr(step, "parse_mode", None) or "") or None,
                    }
                )

            return {"enabled": bool(getattr(seq, "enabled", False)), "steps": steps_out}

    async def upsert_onboarding_sequence_steps(
        self,
        *,
        group_id: int,
        admin_id: int,
        enabled: bool,
        steps: list[dict],
    ) -> dict:
        """
        Upsert multiple onboarding steps (order = list index + 1).

        Notes: We do NOT delete existing steps (to avoid FK issues with historical `sequence_run_steps`).
        Steps beyond the provided list are blanked out (text=" ") so they won't send.
        """
        enabled = bool(enabled)
        steps = steps or []
        if len(steps) > 10:
            raise ValueError("too many steps (max 10)")

        normalized: list[dict] = []
        for idx, raw in enumerate(steps, start=1):
            delay_seconds = int((raw or {}).get("delay_seconds") or 0)
            delay_seconds = max(0, min(delay_seconds, 7 * 24 * 3600))

            parse_mode = (raw or {}).get("parse_mode")
            parse_mode_norm: str | None
            if parse_mode is None or parse_mode == "":
                parse_mode_norm = None
            elif parse_mode in ("Markdown", "HTML"):
                parse_mode_norm = str(parse_mode)
            else:
                raise ValueError("parse_mode must be Markdown|HTML|null")

            text = str((raw or {}).get("text") or "").strip()
            if len(text) > 4096:
                raise ValueError("step text is too long")

            normalized.append(
                {
                    "step_order": idx,
                    "delay_seconds": delay_seconds,
                    "text": text,
                    "parse_mode": parse_mode_norm,
                }
            )

        if enabled:
            if not normalized or not normalized[0].get("text"):
                raise ValueError("step 1 text is required when enabled")

        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(
                select(Sequence).where(Sequence.group_id == int(group_id), Sequence.key == "onboarding_verified")
            )
            seq = result.scalar_one_or_none()
            if not seq:
                seq = Sequence(
                    group_id=int(group_id),
                    key="onboarding_verified",
                    name="Onboarding after verification",
                    trigger="user_verified",
                    enabled=enabled,
                    created_by=int(admin_id),
                    created_at=now,
                    updated_at=now,
                )
                session.add(seq)
                await session.flush()
            else:
                seq.enabled = enabled
                seq.updated_at = now

            steps_result = await session.execute(
                select(SequenceStep).where(SequenceStep.sequence_id == int(seq.id)).order_by(SequenceStep.step_order)
            )
            existing = {int(s.step_order): s for s in steps_result.scalars().all()}

            for step_data in normalized:
                order = int(step_data["step_order"])
                step = existing.get(order)
                if not step:
                    step = SequenceStep(
                        sequence_id=int(seq.id),
                        step_order=order,
                        delay_seconds=int(step_data["delay_seconds"]),
                        text=str(step_data["text"] or " "),
                        parse_mode=step_data["parse_mode"],
                        disable_web_page_preview=True,
                        created_at=now,
                    )
                    session.add(step)
                else:
                    step.delay_seconds = int(step_data["delay_seconds"])
                    step.text = str(step_data["text"] or " ")
                    step.parse_mode = step_data["parse_mode"]
                    step.disable_web_page_preview = True

            # Blank out extra existing steps so they won't send.
            max_order = len(normalized)
            for order, step in existing.items():
                if order <= max_order:
                    continue
                step.delay_seconds = 0
                step.text = " "
                step.parse_mode = None
                step.disable_web_page_preview = True

        return await self.get_onboarding_sequence_steps(int(group_id))

    async def start_sequence_by_key(
        self,
        *,
        group_id: int,
        telegram_id: int,
        sequence_key: str,
        trigger_key: str,
    ) -> int | None:
        """
        Start a specific sequence for a user (idempotent per trigger_key).

        Returns:
            run_id if started, else None (missing/disabled/already started).
        """
        sequence_key = (sequence_key or "").strip()
        if not sequence_key:
            raise ValueError("sequence_key is empty")

        trigger_key = (trigger_key or "").strip()
        if not trigger_key:
            raise ValueError("trigger_key is empty")

        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(
                select(Sequence).where(Sequence.group_id == int(group_id), Sequence.key == str(sequence_key))
            )
            seq = result.scalar_one_or_none()
            if not seq or not getattr(seq, "enabled", False):
                return None

            run = SequenceRun(
                sequence_id=int(seq.id),
                telegram_id=int(telegram_id),
                trigger_key=str(trigger_key),
                status="running",
                started_at=now,
                finished_at=None,
                last_error=None,
            )
            session.add(run)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                return None

            steps_result = await session.execute(
                select(SequenceStep).where(SequenceStep.sequence_id == int(seq.id)).order_by(SequenceStep.step_order)
            )
            steps = [s for s in steps_result.scalars().all() if str(getattr(s, "text", "") or "").strip()]
            if not steps:
                run.status = "completed"
                run.finished_at = now
                return int(run.id)

            for step in steps:
                run_at = now + timedelta(seconds=int(getattr(step, "delay_seconds", 0) or 0))
                run_step = SequenceRunStep(
                    run_id=int(run.id),
                    step_id=int(step.id),
                    status="pending",
                    run_at=run_at,
                    attempts=0,
                    sent_at=None,
                    telegram_message_id=None,
                    error=None,
                    created_at=now,
                )
                session.add(run_step)
                await session.flush()
                await self.jobs.enqueue("sequence_step", {"run_step_id": int(run_step.id)}, run_at=run_at)

            return int(run.id)

    async def trigger_user_verified(self, *, bot: Bot, group_id: int, telegram_id: int) -> None:
        """
        Trigger enabled sequences for this group on user verification.

        Idempotent per (sequence_id, telegram_id, trigger_key="user_verified").
        """
        now = datetime.utcnow()
        async with db.session() as session:
            seq_result = await session.execute(
                select(Sequence).where(
                    Sequence.group_id == int(group_id),
                    Sequence.trigger == "user_verified",
                    Sequence.enabled.is_(True),
                )
            )
            sequences = list(seq_result.scalars().all())

            for seq in sequences:
                run = SequenceRun(
                    sequence_id=int(seq.id),
                    telegram_id=int(telegram_id),
                    trigger_key="user_verified",
                    status="running",
                    started_at=now,
                    finished_at=None,
                    last_error=None,
                )
                session.add(run)
                try:
                    await session.flush()
                except IntegrityError:
                    await session.rollback()
                    continue

                steps_result = await session.execute(
                    select(SequenceStep).where(SequenceStep.sequence_id == int(seq.id)).order_by(SequenceStep.step_order)
                )
                steps = [s for s in steps_result.scalars().all() if str(getattr(s, "text", "") or "").strip()]
                if not steps:
                    run.status = "completed"
                    run.finished_at = now
                    continue

                for step in steps:
                    run_at = now + timedelta(seconds=int(getattr(step, "delay_seconds", 0) or 0))
                    run_step = SequenceRunStep(
                        run_id=int(run.id),
                        step_id=int(step.id),
                        status="pending",
                        run_at=run_at,
                        attempts=0,
                        sent_at=None,
                        telegram_message_id=None,
                        error=None,
                        created_at=now,
                    )
                    session.add(run_step)
                    await session.flush()
                    await self.jobs.enqueue("sequence_step", {"run_step_id": int(run_step.id)}, run_at=run_at)

    async def run_step_job(self, bot: Bot, *, run_step_id: int) -> SequenceJobResult:
        now = datetime.utcnow()
        async with db.session() as session:
            run_step = await session.get(SequenceRunStep, int(run_step_id))
            if not run_step:
                return SequenceJobResult(done=True, detail="run_step missing")
            if run_step.status != "pending":
                return SequenceJobResult(done=True, detail=f"run_step status={run_step.status}")

            run = await session.get(SequenceRun, int(run_step.run_id))
            if not run or run.status != "running":
                run_step.status = "cancelled"
                return SequenceJobResult(done=True, detail="run not running")

            step = await session.get(SequenceStep, int(run_step.step_id))
            if not step:
                run_step.status = "failed"
                run_step.error = "step missing"
                run.last_error = "step missing"
                run.status = "failed"
                run.finished_at = now
                return SequenceJobResult(done=True, detail="step missing")
            if not str(getattr(step, "text", "") or "").strip():
                run_step.status = "cancelled"
                return SequenceJobResult(done=True, detail="step empty")

            seq = await session.get(Sequence, int(run.sequence_id))
            if not seq or not getattr(seq, "enabled", False):
                run_step.status = "cancelled"
                return SequenceJobResult(done=True, detail="sequence disabled")

            run_step.attempts = int(getattr(run_step, "attempts", 0) or 0) + 1

            try:
                msg = await bot.send_message(
                    chat_id=int(run.telegram_id),
                    text=str(step.text),
                    parse_mode=(str(step.parse_mode) if step.parse_mode else None),
                    disable_web_page_preview=bool(getattr(step, "disable_web_page_preview", True)),
                )
                run_step.status = "sent"
                run_step.sent_at = now
                run_step.telegram_message_id = int(getattr(msg, "message_id", 0) or 0) or None
            except TelegramRetryAfter as e:
                return SequenceJobResult(done=False, retry_after_seconds=int(e.retry_after), detail="telegram rate limit")
            except Exception as e:
                run_step.status = "failed"
                run_step.error = str(e)[:2000]
                run.last_error = str(e)[:2000]

            # Finalize run if no pending steps left.
            pending_count_result = await session.execute(
                select(func.count())
                .select_from(SequenceRunStep)
                .where(SequenceRunStep.run_id == int(run.id), SequenceRunStep.status == "pending")
            )
            pending = int(pending_count_result.scalar() or 0)
            if pending <= 0:
                failed_count_result = await session.execute(
                    select(func.count())
                    .select_from(SequenceRunStep)
                    .where(SequenceRunStep.run_id == int(run.id), SequenceRunStep.status == "failed")
                )
                failed = int(failed_count_result.scalar() or 0)
                run.status = "failed" if failed else "completed"
                run.finished_at = now

        return SequenceJobResult(done=True, detail="sent")
