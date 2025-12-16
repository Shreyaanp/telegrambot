"""Group settings service - manage per-group configuration."""
import logging
from typing import Optional
from sqlalchemy import select

from database.db import db
from database.models import Group

logger = logging.getLogger(__name__)


class GroupService:
    """Manage group-level settings such as verification, welcome, and antiflood."""
    
    async def get_or_create_group(self, group_id: int) -> Group:
        """Fetch group settings, creating defaults if missing."""
        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == group_id))
            group = result.scalar_one_or_none()
            
            if not group:
                group = Group(group_id=group_id)
                session.add(group)
                await session.commit()
                await session.refresh(group)
                logger.info(f"Created default settings for group {group_id}")
            
            return group

    async def register_group(self, group_id: int, group_name: Optional[str] = None) -> Group:
        """Ensure group exists and update name."""
        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == group_id))
            group = result.scalar_one_or_none()
            if not group:
                group = Group(group_id=group_id, group_name=group_name)
                session.add(group)
            else:
                if group_name and group.group_name != group_name:
                    group.group_name = group_name
            await session.commit()
            await session.refresh(group)
            return group

    async def list_groups(self) -> list[Group]:
        """List all known groups."""
        async with db.session() as session:
            result = await session.execute(select(Group))
            return list(result.scalars().all())

    async def set_cleanup(self, group_id: int, enabled: bool) -> Group:
        """Toggle auto-delete verification messages flag stored in group."""
        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == group_id))
            group = result.scalar_one_or_none()
            if not group:
                group = Group(group_id=group_id)
                session.add(group)
            group.auto_delete_messages = enabled  # assumes column exists; if not, extend model later
            await session.commit()
            await session.refresh(group)
            return group
    
    async def update_setting(
        self,
        group_id: int,
        *,
        verification_timeout: Optional[int] = None,
        action_on_timeout: Optional[str] = None,  # "kick" or "mute"
        antiflood_limit: Optional[int] = None,
        antiflood_enabled: Optional[bool] = None,
        welcome_enabled: Optional[bool] = None,
        verification_enabled: Optional[bool] = None,
    ) -> Group:
        """Update one or more settings for a group."""
        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == group_id))
            group = result.scalar_one_or_none()
            
            if not group:
                group = Group(group_id=group_id)
                session.add(group)
            
            if verification_timeout is not None:
                group.verification_timeout = max(30, verification_timeout)
            if action_on_timeout is not None:
                # Group model stores kick_unverified; map kick->True, mute->False
                group.kick_unverified = (action_on_timeout == "kick")
            if antiflood_limit is not None:
                group.antiflood_limit = max(1, antiflood_limit)
                group.antiflood_enabled = True
            if antiflood_enabled is not None:
                group.antiflood_enabled = antiflood_enabled
            if welcome_enabled is not None:
                group.welcome_enabled = welcome_enabled
            if verification_enabled is not None:
                group.verification_enabled = verification_enabled
            
            await session.commit()
            await session.refresh(group)
            logger.info(f"Updated settings for group {group_id}")
            return group
