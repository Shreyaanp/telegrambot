"""Whitelist service - manage users who bypass verification."""
import logging
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, and_, delete

from database.db import db
from database.models import Whitelist

logger = logging.getLogger(__name__)


class WhitelistService:
    """
    Whitelist management service.
    
    Users on the whitelist bypass verification requirements.
    """
    
    async def add_to_whitelist(
        self,
        group_id: int,
        user_id: int,
        admin_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """
        Add a user to the whitelist.
        
        Args:
            group_id: Group ID
            user_id: User to whitelist
            admin_id: Admin performing the action
            reason: Optional reason
            
        Returns:
            True if added, False if already whitelisted
        """
        async with db.session() as session:
            # Check if already whitelisted
            result = await session.execute(
                select(Whitelist)
                .where(
                    and_(
                        Whitelist.group_id == group_id,
                        Whitelist.telegram_id == user_id
                    )
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                logger.info(f"User {user_id} already whitelisted in group {group_id}")
                return False
            
            # Add to whitelist
            whitelist_entry = Whitelist(
                group_id=group_id,
                telegram_id=user_id,
                added_by=admin_id,
                reason=reason,
                added_at=datetime.utcnow()
            )
            session.add(whitelist_entry)
            await session.commit()
            
            logger.info(f"User {user_id} added to whitelist in group {group_id}")
            return True
    
    async def remove_from_whitelist(
        self,
        group_id: int,
        user_id: int
    ) -> bool:
        """
        Remove a user from the whitelist.
        
        Args:
            group_id: Group ID
            user_id: User to remove
            
        Returns:
            True if removed, False if not whitelisted
        """
        async with db.session() as session:
            result = await session.execute(
                delete(Whitelist)
                .where(
                    and_(
                        Whitelist.group_id == group_id,
                        Whitelist.telegram_id == user_id
                    )
                )
            )
            await session.commit()
            
            removed = result.rowcount > 0
            if removed:
                logger.info(f"User {user_id} removed from whitelist in group {group_id}")
            else:
                logger.info(f"User {user_id} was not whitelisted in group {group_id}")
            
            return removed
    
    async def is_whitelisted(self, group_id: int, user_id: int) -> bool:
        """
        Check if a user is whitelisted in a group.
        
        Args:
            group_id: Group ID
            user_id: User ID
            
        Returns:
            True if whitelisted, False otherwise
        """
        async with db.session() as session:
            result = await session.execute(
                select(Whitelist)
                .where(
                    and_(
                        Whitelist.group_id == group_id,
                        Whitelist.telegram_id == user_id
                    )
                )
            )
            return result.scalar_one_or_none() is not None
    
    async def get_whitelist(self, group_id: int) -> List[Whitelist]:
        """
        Get all whitelisted users in a group.
        
        Args:
            group_id: Group ID
            
        Returns:
            List of Whitelist entries
        """
        async with db.session() as session:
            result = await session.execute(
                select(Whitelist)
                .where(Whitelist.group_id == group_id)
                .order_by(Whitelist.added_at.desc())
            )
            return list(result.scalars().all())
    
    async def get_whitelist_count(self, group_id: int) -> int:
        """
        Get count of whitelisted users in a group.
        
        Args:
            group_id: Group ID
            
        Returns:
            Number of whitelisted users
        """
        async with db.session() as session:
            from sqlalchemy import func
            result = await session.execute(
                select(func.count(Whitelist.id))
                .where(Whitelist.group_id == group_id)
            )
            return result.scalar()

