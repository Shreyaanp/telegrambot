"""Metrics service - track admin actions and verification stats (in-memory)."""
import asyncio
import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class MetricsService:
    """Simple in-memory metrics store (non-persistent)."""
    def __init__(self):
        self.admin_actions = Counter()  # (action, group_id) -> count
        self.verification_outcomes = Counter()  # outcome -> count
        self.api_errors = Counter()  # name -> count
        self.last_update_at: datetime | None = None
        self.lock = asyncio.Lock()
    
    async def incr_admin_action(self, action: str, group_id: int):
        async with self.lock:
            self.admin_actions[(action, group_id)] += 1
            self.last_update_at = datetime.utcnow()
    
    async def incr_verification(self, outcome: str):
        async with self.lock:
            self.verification_outcomes[outcome] += 1
            self.last_update_at = datetime.utcnow()

    async def incr_api_error(self, name: str):
        async with self.lock:
            self.api_errors[name] += 1
            self.last_update_at = datetime.utcnow()

    async def snapshot(self) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int], datetime | None]:
        async with self.lock:
            # Aggregate admin actions by action name
            action_totals = defaultdict(int)
            for (action, _gid), count in self.admin_actions.items():
                action_totals[action] += count
            return dict(action_totals), dict(self.verification_outcomes), dict(self.api_errors), self.last_update_at
