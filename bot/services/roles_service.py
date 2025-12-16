"""Roles service - manage scoped permissions."""
import logging
from typing import List, Optional
from sqlalchemy import select, delete

from database.db import db
from database.models import Permission

logger = logging.getLogger(__name__)


ROLE_PRESETS = {
    "moderator": dict(
        can_verify=True,
        can_kick=True,
        can_ban=True,
        can_warn=True,
        can_manage_notes=True,
        can_manage_filters=True,
    ),
    "helper": dict(
        can_verify=True,
        can_kick=False,
        can_ban=False,
        can_warn=True,
        can_manage_notes=False,
        can_manage_filters=False,
    ),
}


class RolesService:
    """Manage custom roles/permissions."""
    
    async def add_role(self, group_id: int, user_id: int, role: str, granted_by: int) -> Permission:
        """Assign a role to a user in a group."""
        role = role.lower()
        flags = ROLE_PRESETS.get(role, {})
        async with db.session() as session:
            # Check existing
            result = await session.execute(
                select(Permission).where(
                    Permission.group_id == group_id,
                    Permission.telegram_id == user_id
                )
            )
            perm = result.scalar_one_or_none()
            if not perm:
                perm = Permission(
                    group_id=group_id,
                    telegram_id=user_id,
                    role=role,
                    granted_by=granted_by,
                    **flags
                )
                session.add(perm)
            else:
                perm.role = role
                for k, v in flags.items():
                    setattr(perm, k, v)
                perm.granted_by = granted_by
            await session.commit()
            await session.refresh(perm)
            logger.info(f"Assigned role {role} to user {user_id} in group {group_id}")
            return perm
    
    async def remove_role(self, group_id: int, user_id: int) -> bool:
        """Remove role assignment."""
        async with db.session() as session:
            result = await session.execute(
                delete(Permission).where(
                    Permission.group_id == group_id,
                    Permission.telegram_id == user_id
                )
            )
            await session.commit()
            return result.rowcount > 0
    
    async def list_roles(self, group_id: int) -> List[Permission]:
        """List roles in a group."""
        async with db.session() as session:
            result = await session.execute(
                select(Permission).where(Permission.group_id == group_id)
            )
            return list(result.scalars().all())
