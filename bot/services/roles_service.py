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
        can_manage_settings=True,
        can_manage_locks=True,
        can_manage_roles=False,
        can_view_status=True,
        can_view_logs=True,
    ),
    "helper": dict(
        can_verify=True,
        can_kick=False,
        can_ban=False,
        can_warn=True,
        can_manage_notes=False,
        can_manage_filters=False,
        can_manage_settings=False,
        can_manage_locks=False,
        can_manage_roles=False,
        can_view_status=False,
        can_view_logs=False,
    ),
}


class RolesService:
    """Manage custom roles/permissions."""

    _FLAG_FIELDS = (
        "can_verify",
        "can_kick",
        "can_ban",
        "can_warn",
        "can_manage_notes",
        "can_manage_filters",
        "can_manage_settings",
        "can_manage_locks",
        "can_manage_roles",
        "can_view_status",
        "can_view_logs",
    )

    _KEY_TO_FIELD = {
        "verify": "can_verify",
        "kick": "can_kick",
        "ban": "can_ban",
        "warn": "can_warn",
        "notes": "can_manage_notes",
        "filters": "can_manage_filters",
        "settings": "can_manage_settings",
        "locks": "can_manage_locks",
        "roles": "can_manage_roles",
        "status": "can_view_status",
        "logs": "can_view_logs",
    }
    
    async def add_role(self, group_id: int, user_id: int, role: str, granted_by: int) -> Permission:
        """Assign a role to a user in a group."""
        role = role.lower()
        flags = ROLE_PRESETS.get(role)
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
                    **(flags or {})
                )
                session.add(perm)
            else:
                perm.role = role
                if flags is None:
                    # Unknown/custom role name: reset to least-privilege by default.
                    for field in self._FLAG_FIELDS:
                        setattr(perm, field, False)
                else:
                    for field in self._FLAG_FIELDS:
                        setattr(perm, field, False)
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

    async def get_role(self, group_id: int, user_id: int) -> Optional[Permission]:
        async with db.session() as session:
            result = await session.execute(
                select(Permission).where(
                    Permission.group_id == group_id,
                    Permission.telegram_id == user_id,
                )
            )
            return result.scalar_one_or_none()

    async def set_permission(
        self,
        *,
        group_id: int,
        user_id: int,
        permission_key: str,
        enabled: bool,
        granted_by: int,
    ) -> bool:
        field = self._KEY_TO_FIELD.get((permission_key or "").lower())
        if not field:
            return False

        async with db.session() as session:
            result = await session.execute(
                select(Permission).where(
                    Permission.group_id == group_id,
                    Permission.telegram_id == user_id,
                )
            )
            perm = result.scalar_one_or_none()
            if not perm:
                perm = Permission(
                    group_id=group_id,
                    telegram_id=user_id,
                    role="custom",
                    granted_by=granted_by,
                )
                for f in self._FLAG_FIELDS:
                    setattr(perm, f, False)
                session.add(perm)

            setattr(perm, field, bool(enabled))
            perm.granted_by = granted_by
            await session.commit()
            return True

    def format_flags(self, perm: Permission) -> str:
        pairs = [
            ("verify", perm.can_verify),
            ("kick", perm.can_kick),
            ("ban", perm.can_ban),
            ("warn", perm.can_warn),
            ("notes", perm.can_manage_notes),
            ("filters", perm.can_manage_filters),
            ("settings", perm.can_manage_settings),
            ("locks", perm.can_manage_locks),
            ("roles", perm.can_manage_roles),
            ("status", perm.can_view_status),
            ("logs", perm.can_view_logs),
        ]
        return "\n".join(f"- `{k}`: {'✅' if v else '❌'}" for k, v in pairs)
