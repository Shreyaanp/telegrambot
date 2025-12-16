"""Lock service - manage per-group content locks (links/media)."""
import logging
from typing import Optional
from sqlalchemy import select

from database.db import db
from database.models import Group

logger = logging.getLogger(__name__)


class LockService:
    """Manage lock/unlock for links/media."""
    async def set_lock(self, group_id: int, lock_links: Optional[bool] = None, lock_media: Optional[bool] = None) -> Group:
        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == group_id))
            group = result.scalar_one_or_none()
            if not group:
                group = Group(group_id=group_id)
                session.add(group)
            if lock_links is not None:
                group.lock_links = lock_links
            if lock_media is not None:
                group.lock_media = lock_media
            await session.commit()
            await session.refresh(group)
            return group

    async def get_locks(self, group_id: int) -> tuple[bool, bool]:
        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == group_id))
            group = result.scalar_one_or_none()
            if not group:
                return False, False
            return bool(getattr(group, "lock_links", False)), bool(getattr(group, "lock_media", False))
