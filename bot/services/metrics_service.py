"""Metrics service - track admin actions and verification stats (persistent)."""
import asyncio
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, Tuple

from sqlalchemy import select, text

from database.db import db
from database.models import MetricCounter

logger = logging.getLogger(__name__)


class MetricsService:
    """Small metrics store with Postgres-backed counters (survives restarts)."""

    def __init__(self, *, persist: bool = True):
        self.admin_actions = Counter()  # (action, group_id) -> count
        self.verification_outcomes = Counter()  # outcome -> count
        self.api_errors = Counter()  # name -> count
        self.last_update_at: datetime | None = None
        self.lock = asyncio.Lock()
        self.persist = persist

    async def _incr_persistent(self, key: str, delta: int = 1) -> None:
        if not self.persist:
            return
        try:
            async with db.session() as session:
                await session.execute(
                    text(
                        "INSERT INTO metric_counters(key, value, updated_at) "
                        "VALUES (:key, :delta, NOW()) "
                        "ON CONFLICT (key) DO UPDATE "
                        "SET value = metric_counters.value + :delta, updated_at = NOW()"
                    ),
                    {"key": key, "delta": int(delta)},
                )
        except Exception:
            return
    
    async def incr_admin_action(self, action: str, group_id: int):
        async with self.lock:
            self.admin_actions[(action, group_id)] += 1
            self.last_update_at = datetime.utcnow()
        await self._incr_persistent(f"admin_action:{action}", 1)
    
    async def incr_verification(self, outcome: str):
        async with self.lock:
            self.verification_outcomes[outcome] += 1
            self.last_update_at = datetime.utcnow()
        await self._incr_persistent(f"verification:{outcome}", 1)

    async def incr_api_error(self, name: str):
        async with self.lock:
            self.api_errors[name] += 1
            self.last_update_at = datetime.utcnow()
        await self._incr_persistent(f"api_error:{name}", 1)

    async def snapshot(self) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int], datetime | None]:
        try:
            async with db.session() as session:
                result = await session.execute(select(MetricCounter))
                rows = list(result.scalars().all())

            admin_actions: dict[str, int] = {}
            verification_outcomes: dict[str, int] = {}
            api_errors: dict[str, int] = {}
            last_update_at: datetime | None = None

            for row in rows:
                try:
                    if row.updated_at and (last_update_at is None or row.updated_at > last_update_at):
                        last_update_at = row.updated_at
                except Exception:
                    pass

                key = str(getattr(row, "key", "") or "")
                value = int(getattr(row, "value", 0) or 0)
                if key.startswith("admin_action:"):
                    admin_actions[key.split(":", 1)[1]] = value
                elif key.startswith("verification:"):
                    verification_outcomes[key.split(":", 1)[1]] = value
                elif key.startswith("api_error:"):
                    api_errors[key.split(":", 1)[1]] = value

            return admin_actions, verification_outcomes, api_errors, last_update_at
        except Exception:
            # Fallback to in-memory (best-effort).
            async with self.lock:
                action_totals = defaultdict(int)
                for (action, _gid), count in self.admin_actions.items():
                    action_totals[action] += count
                return dict(action_totals), dict(self.verification_outcomes), dict(self.api_errors), self.last_update_at
