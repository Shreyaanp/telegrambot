"""Permission service - handles permission and role operations."""
import logging
from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, delete, or_
from aiogram import Bot
from aiogram.types import ChatMember
from aiogram.enums import ChatMemberStatus
from database import Database, Permission, Warning, Whitelist

logger = logging.getLogger(__name__)


class PermissionService:
    """Service for managing permissions and roles."""
    
    def __init__(self, db: Database):
        """
        Initialize permission service.
        
        Args:
            db: Database instance
        """
        self.db = db
        self.logger = logging.getLogger(__name__)
    
    async def is_admin(self, bot: Bot, group_id: int, telegram_id: int) -> bool:
        """
        Check if user is a Telegram admin in the group.
        
        Args:
            bot: Bot instance
            group_id: Group ID
            telegram_id: User's Telegram ID
        
        Returns:
            True if user is admin, False otherwise
        """
        try:
            member: ChatMember = await bot.get_chat_member(group_id, telegram_id)
            return member.status in [ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR]
        except Exception as e:
            self.logger.error(f"Error checking admin status for {telegram_id} in {group_id}: {e}")
            return False
    
    async def has_custom_permission(
        self,
        group_id: int,
        telegram_id: int,
        permission: str
    ) -> bool:
        """
        Check if user has a custom permission in the group.
        
        Args:
            group_id: Group ID
            telegram_id: User's Telegram ID
            permission: Permission name (can_verify, can_kick, can_ban, etc.)
        
        Returns:
            True if user has permission, False otherwise
        """
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(Permission).where(
                        Permission.group_id == group_id,
                        Permission.telegram_id == telegram_id
                    )
                )
                perm = result.scalar_one_or_none()
                
                if not perm:
                    return False
                
                # Check the specific permission
                return getattr(perm, permission, False)
                
        except Exception as e:
            self.logger.error(f"Error checking permission for {telegram_id} in {group_id}: {e}")
            return False
    
    async def can_perform_action(
        self,
        bot: Bot,
        group_id: int,
        telegram_id: int,
        action: str
    ) -> bool:
        """
        Check if user can perform an action (hybrid: Telegram admin OR custom permission).
        
        Args:
            bot: Bot instance
            group_id: Group ID
            telegram_id: User's Telegram ID
            action: Action name (verify, kick, ban, warn, settings)
        
        Returns:
            True if user can perform action, False otherwise
        """
        # Telegram admins can do everything
        if await self.is_admin(bot, group_id, telegram_id):
            return True
        
        # Check custom permissions
        permission_field = f"can_{action}"
        return await self.has_custom_permission(group_id, telegram_id, permission_field)
    
    async def grant_permission(
        self,
        group_id: int,
        telegram_id: int,
        role: str,
        granted_by: int,
        **permissions
    ) -> Optional[Permission]:
        """
        Grant custom permissions to a user.
        
        Args:
            group_id: Group ID
            telegram_id: User's Telegram ID
            role: Role name (owner, admin, moderator)
            granted_by: Admin who granted the permission
            **permissions: Permission flags (can_verify=True, etc.)
        
        Returns:
            Permission object or None if failed
        """
        try:
            async with self.db.session() as session:
                # Check if permission exists
                result = await session.execute(
                    select(Permission).where(
                        Permission.group_id == group_id,
                        Permission.telegram_id == telegram_id
                    )
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update existing permission
                    existing.role = role
                    for key, value in permissions.items():
                        setattr(existing, key, value)
                    await session.commit()
                    self.logger.info(f"Updated permissions for {telegram_id} in group {group_id}")
                    return existing
                else:
                    # Create new permission
                    perm = Permission(
                        group_id=group_id,
                        telegram_id=telegram_id,
                        role=role,
                        granted_by=granted_by,
                        granted_at=datetime.utcnow(),
                        **permissions
                    )
                    session.add(perm)
                    await session.commit()
                    self.logger.info(f"Granted permissions to {telegram_id} in group {group_id}")
                    return perm
                    
        except Exception as e:
            self.logger.error(f"Error granting permission to {telegram_id} in {group_id}: {e}", exc_info=True)
            return None
    
    async def revoke_permission(self, group_id: int, telegram_id: int) -> bool:
        """
        Revoke custom permissions from a user.
        
        Args:
            group_id: Group ID
            telegram_id: User's Telegram ID
        
        Returns:
            True if revoked successfully, False otherwise
        """
        try:
            async with self.db.session() as session:
                await session.execute(
                    delete(Permission).where(
                        Permission.group_id == group_id,
                        Permission.telegram_id == telegram_id
                    )
                )
                await session.commit()
                self.logger.info(f"Revoked permissions from {telegram_id} in group {group_id}")
                return True
        except Exception as e:
            self.logger.error(f"Error revoking permission from {telegram_id} in {group_id}: {e}", exc_info=True)
            return False
    
    # Whitelist management
    
    async def is_whitelisted(self, group_id: int, telegram_id: int) -> bool:
        """Check if user is whitelisted in the group."""
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(Whitelist).where(
                        Whitelist.group_id == group_id,
                        Whitelist.telegram_id == telegram_id
                    )
                )
                return result.scalar_one_or_none() is not None
        except Exception as e:
            self.logger.error(f"Error checking whitelist for {telegram_id} in {group_id}: {e}")
            return False
    
    async def add_to_whitelist(
        self,
        group_id: int,
        telegram_id: int,
        added_by: int,
        reason: Optional[str] = None
    ) -> Optional[Whitelist]:
        """Add user to whitelist."""
        try:
            async with self.db.session() as session:
                # Check if already whitelisted
                result = await session.execute(
                    select(Whitelist).where(
                        Whitelist.group_id == group_id,
                        Whitelist.telegram_id == telegram_id
                    )
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    return existing
                
                whitelist_entry = Whitelist(
                    group_id=group_id,
                    telegram_id=telegram_id,
                    added_by=added_by,
                    reason=reason,
                    added_at=datetime.utcnow()
                )
                session.add(whitelist_entry)
                await session.commit()
                self.logger.info(f"Added {telegram_id} to whitelist in group {group_id}")
                return whitelist_entry
                
        except Exception as e:
            self.logger.error(f"Error adding {telegram_id} to whitelist in {group_id}: {e}", exc_info=True)
            return None
    
    async def remove_from_whitelist(self, group_id: int, telegram_id: int) -> bool:
        """Remove user from whitelist."""
        try:
            async with self.db.session() as session:
                await session.execute(
                    delete(Whitelist).where(
                        Whitelist.group_id == group_id,
                        Whitelist.telegram_id == telegram_id
                    )
                )
                await session.commit()
                self.logger.info(f"Removed {telegram_id} from whitelist in group {group_id}")
                return True
        except Exception as e:
            self.logger.error(f"Error removing {telegram_id} from whitelist in {group_id}: {e}", exc_info=True)
            return False
    
    async def get_whitelist(self, group_id: int) -> List[Whitelist]:
        """Get all whitelisted users in a group."""
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(Whitelist).where(Whitelist.group_id == group_id)
                )
                return result.scalars().all()
        except Exception as e:
            self.logger.error(f"Error getting whitelist for group {group_id}: {e}")
            return []
    
    # Warning management
    
    async def add_warning(
        self,
        group_id: int,
        telegram_id: int,
        warned_by: int,
        reason: Optional[str] = None
    ) -> Optional[Warning]:
        """Add a warning to a user."""
        try:
            async with self.db.session() as session:
                warning = Warning(
                    group_id=group_id,
                    telegram_id=telegram_id,
                    warned_by=warned_by,
                    reason=reason,
                    warned_at=datetime.utcnow()
                )
                session.add(warning)
                await session.commit()
                self.logger.info(f"Added warning to {telegram_id} in group {group_id}")
                return warning
        except Exception as e:
            self.logger.error(f"Error adding warning to {telegram_id} in {group_id}: {e}", exc_info=True)
            return None
    
    async def get_warning_count(self, group_id: int, telegram_id: int) -> int:
        """Get number of warnings for a user in a group."""
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(Warning).where(
                        Warning.group_id == group_id,
                        Warning.telegram_id == telegram_id
                    )
                )
                return len(result.scalars().all())
        except Exception as e:
            self.logger.error(f"Error getting warning count for {telegram_id} in {group_id}: {e}")
            return 0
    
    async def clear_warnings(self, group_id: int, telegram_id: int) -> bool:
        """Clear all warnings for a user in a group."""
        try:
            async with self.db.session() as session:
                await session.execute(
                    delete(Warning).where(
                        Warning.group_id == group_id,
                        Warning.telegram_id == telegram_id
                    )
                )
                await session.commit()
                self.logger.info(f"Cleared warnings for {telegram_id} in group {group_id}")
                return True
        except Exception as e:
            self.logger.error(f"Error clearing warnings for {telegram_id} in {group_id}: {e}")
            return False
    
    async def get_warnings(self, group_id: int, telegram_id: int) -> List[Warning]:
        """Get all warnings for a user in a group."""
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(Warning).where(
                        Warning.group_id == group_id,
                        Warning.telegram_id == telegram_id
                    ).order_by(Warning.warned_at.desc())
                )
                return result.scalars().all()
        except Exception as e:
            self.logger.error(f"Error getting warnings for {telegram_id} in {group_id}: {e}")
            return []

