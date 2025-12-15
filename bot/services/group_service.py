"""Group service - handles group-related database operations."""
import logging
from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, update, delete
from database import Database, Group, GroupMember

logger = logging.getLogger(__name__)


class GroupService:
    """Service for managing group operations."""
    
    def __init__(self, db: Database):
        """
        Initialize group service.
        
        Args:
            db: Database instance
        """
        self.db = db
        self.logger = logging.getLogger(__name__)
    
    async def get_group(self, group_id: int) -> Optional[Group]:
        """
        Get a group by ID.
        
        Args:
            group_id: Telegram group ID
        
        Returns:
            Group object or None if not found
        """
        try:
            async with self.db.session() as session:
                return await session.get(Group, group_id)
        except Exception as e:
            self.logger.error(f"Error getting group {group_id}: {e}", exc_info=True)
            return None
    
    async def create_group(
        self,
        group_id: int,
        group_name: Optional[str] = None,
        verification_enabled: bool = True,
        auto_verify_on_join: bool = True,
        verification_timeout: int = 120,
        kick_on_timeout: bool = True
    ) -> Optional[Group]:
        """
        Create a new group or update if exists.
        
        Args:
            group_id: Telegram group ID
            group_name: Group name
            verification_enabled: Whether verification is enabled
            auto_verify_on_join: Whether to auto-verify on join
            verification_timeout: Verification timeout in seconds
            kick_on_timeout: Whether to kick on timeout
        
        Returns:
            Created/updated Group object or None if failed
        """
        try:
            async with self.db.session() as session:
                # Check if group exists
                existing = await session.get(Group, group_id)
                
                if existing:
                    # Update existing group
                    existing.group_name = group_name
                    await session.commit()
                    self.logger.info(f"Updated group: {group_id}")
                    return existing
                else:
                    # Create new group
                    group = Group(
                        group_id=group_id,
                        group_name=group_name,
                        verification_enabled=verification_enabled,
                        auto_verify_on_join=auto_verify_on_join,
                        verification_timeout=verification_timeout,
                        kick_on_timeout=kick_on_timeout
                    )
                    session.add(group)
                    await session.commit()
                    self.logger.info(f"Created group: {group_id}")
                    return group
                    
        except Exception as e:
            self.logger.error(f"Error creating group {group_id}: {e}", exc_info=True)
            return None
    
    async def update_group_settings(
        self,
        group_id: int,
        **kwargs
    ) -> bool:
        """
        Update group settings.
        
        Args:
            group_id: Telegram group ID
            **kwargs: Settings to update
        
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            async with self.db.session() as session:
                await session.execute(
                    update(Group)
                    .where(Group.group_id == group_id)
                    .values(**kwargs)
                )
                await session.commit()
                self.logger.info(f"Updated settings for group {group_id}: {kwargs}")
                return True
        except Exception as e:
            self.logger.error(f"Error updating group {group_id}: {e}", exc_info=True)
            return False
    
    async def set_welcome_message(self, group_id: int, message: str) -> bool:
        """Set custom welcome message for a group."""
        return await self.update_group_settings(group_id, welcome_message=message)
    
    async def set_rules(self, group_id: int, rules: str) -> bool:
        """Set rules for a group."""
        return await self.update_group_settings(group_id, rules_text=rules)
    
    async def set_verification_timeout(self, group_id: int, timeout: int) -> bool:
        """Set verification timeout for a group."""
        return await self.update_group_settings(group_id, verification_timeout=timeout)
    
    async def set_auto_verify(self, group_id: int, enabled: bool) -> bool:
        """Enable/disable auto-verification on join."""
        return await self.update_group_settings(group_id, auto_verify_on_join=enabled)
    
    async def add_member(
        self,
        group_id: int,
        telegram_id: int,
        verified: bool = False,
        muted: bool = False
    ) -> Optional[GroupMember]:
        """
        Add a member to a group or update if exists.
        
        Args:
            group_id: Telegram group ID
            telegram_id: Telegram user ID
            verified: Whether member is verified
            muted: Whether member is muted
        
        Returns:
            GroupMember object or None if failed
        """
        try:
            async with self.db.session() as session:
                # Check if membership exists
                result = await session.execute(
                    select(GroupMember).where(
                        GroupMember.group_id == group_id,
                        GroupMember.telegram_id == telegram_id
                    )
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update existing membership
                    existing.verified = verified
                    existing.muted = muted
                    await session.commit()
                    return existing
                else:
                    # Create new membership
                    member = GroupMember(
                        group_id=group_id,
                        telegram_id=telegram_id,
                        verified=verified,
                        muted=muted,
                        joined_at=datetime.utcnow()
                    )
                    session.add(member)
                    await session.commit()
                    return member
                    
        except Exception as e:
            self.logger.error(f"Error adding member {telegram_id} to group {group_id}: {e}", exc_info=True)
            return None
    
    async def update_member_verification(
        self,
        group_id: int,
        telegram_id: int,
        verified: bool
    ) -> bool:
        """
        Update member's verification status.
        
        Args:
            group_id: Telegram group ID
            telegram_id: Telegram user ID
            verified: Verification status
        
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            async with self.db.session() as session:
                await session.execute(
                    update(GroupMember)
                    .where(
                        GroupMember.group_id == group_id,
                        GroupMember.telegram_id == telegram_id
                    )
                    .values(verified=verified)
                )
                await session.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error updating verification for {telegram_id} in {group_id}: {e}", exc_info=True)
            return False
    
    async def update_member_mute_status(
        self,
        group_id: int,
        telegram_id: int,
        muted: bool
    ) -> bool:
        """
        Update member's mute status.
        
        Args:
            group_id: Telegram group ID
            telegram_id: Telegram user ID
            muted: Mute status
        
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            async with self.db.session() as session:
                await session.execute(
                    update(GroupMember)
                    .where(
                        GroupMember.group_id == group_id,
                        GroupMember.telegram_id == telegram_id
                    )
                    .values(muted=muted)
                )
                await session.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error updating mute status for {telegram_id} in {group_id}: {e}", exc_info=True)
            return False
    
    async def get_member(self, group_id: int, telegram_id: int) -> Optional[GroupMember]:
        """Get a group member."""
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(GroupMember).where(
                        GroupMember.group_id == group_id,
                        GroupMember.telegram_id == telegram_id
                    )
                )
                return result.scalar_one_or_none()
        except Exception as e:
            self.logger.error(f"Error getting member {telegram_id} from group {group_id}: {e}", exc_info=True)
            return None
    
    async def get_group_members(self, group_id: int) -> List[GroupMember]:
        """Get all members of a group."""
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(GroupMember).where(GroupMember.group_id == group_id)
                )
                return result.scalars().all()
        except Exception as e:
            self.logger.error(f"Error getting members for group {group_id}: {e}", exc_info=True)
            return []
    
    async def get_verified_count(self, group_id: int) -> int:
        """Get count of verified members in a group."""
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(GroupMember).where(
                        GroupMember.group_id == group_id,
                        GroupMember.verified == True
                    )
                )
                return len(result.scalars().all())
        except Exception as e:
            self.logger.error(f"Error getting verified count for group {group_id}: {e}", exc_info=True)
            return 0

