"""User service - handles user-related database operations."""
import logging
from typing import Optional
from datetime import datetime
from sqlalchemy import select, update, delete
from database import Database, User

logger = logging.getLogger(__name__)


class UserService:
    """Service for managing user operations."""
    
    def __init__(self, db: Database):
        """
        Initialize user service.
        
        Args:
            db: Database instance
        """
        self.db = db
        self.logger = logging.getLogger(__name__)
    
    async def get_user(self, telegram_id: int) -> Optional[User]:
        """
        Get a user by telegram ID.
        
        Args:
            telegram_id: Telegram user ID
        
        Returns:
            User object or None if not found
        """
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            self.logger.error(f"Error getting user {telegram_id}: {e}", exc_info=True)
            return None
    
    async def get_user_by_mercle_id(self, mercle_user_id: str) -> Optional[User]:
        """
        Get a user by Mercle user ID.
        
        Args:
            mercle_user_id: Mercle user ID
        
        Returns:
            User object or None if not found
        """
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(User).where(User.mercle_user_id == mercle_user_id)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            self.logger.error(f"Error getting user by mercle_id {mercle_user_id}: {e}", exc_info=True)
            return None
    
    async def create_user(
        self,
        telegram_id: int,
        mercle_user_id: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> Optional[User]:
        """
        Create a new user or update if exists.
        
        Args:
            telegram_id: Telegram user ID
            mercle_user_id: Mercle user ID
            username: Telegram username
            first_name: First name
            last_name: Last name
        
        Returns:
            Created/updated User object or None if failed
        """
        try:
            async with self.db.session() as session:
                # Check if user exists
                existing = await session.get(User, telegram_id)
                
                if existing:
                    # Update existing user
                    existing.mercle_user_id = mercle_user_id
                    existing.username = username
                    existing.first_name = first_name
                    existing.last_name = last_name
                    existing.verified_at = datetime.utcnow()
                    await session.commit()
                    self.logger.info(f"Updated user: {telegram_id}")
                    return existing
                else:
                    # Create new user
                    user = User(
                        telegram_id=telegram_id,
                        mercle_user_id=mercle_user_id,
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        verified_at=datetime.utcnow()
                    )
                    session.add(user)
                    await session.commit()
                    self.logger.info(f"Created user: {telegram_id}")
                    return user
                    
        except Exception as e:
            self.logger.error(f"Error creating user {telegram_id}: {e}", exc_info=True)
            return None
    
    async def is_verified(self, telegram_id: int) -> bool:
        """
        Check if a user is verified.
        
        Args:
            telegram_id: Telegram user ID
        
        Returns:
            True if user is verified, False otherwise
        """
        user = await self.get_user(telegram_id)
        return user is not None
    
    async def update_username(self, telegram_id: int, username: str) -> bool:
        """
        Update user's username.
        
        Args:
            telegram_id: Telegram user ID
            username: New username
        
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            async with self.db.session() as session:
                await session.execute(
                    update(User)
                    .where(User.telegram_id == telegram_id)
                    .values(username=username)
                )
                await session.commit()
                self.logger.info(f"Updated username for user {telegram_id}")
                return True
        except Exception as e:
            self.logger.error(f"Error updating username for {telegram_id}: {e}", exc_info=True)
            return False
    
    async def update_reputation(self, telegram_id: int, reputation: int) -> bool:
        """
        Update user's global reputation score.
        
        Args:
            telegram_id: Telegram user ID
            reputation: New reputation score
        
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            async with self.db.session() as session:
                await session.execute(
                    update(User)
                    .where(User.telegram_id == telegram_id)
                    .values(global_reputation=reputation)
                )
                await session.commit()
                self.logger.info(f"Updated reputation for user {telegram_id}: {reputation}")
                return True
        except Exception as e:
            self.logger.error(f"Error updating reputation for {telegram_id}: {e}", exc_info=True)
            return False
    
    async def delete_user(self, telegram_id: int) -> bool:
        """
        Delete a user (use with caution!).
        
        Args:
            telegram_id: Telegram user ID
        
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            async with self.db.session() as session:
                await session.execute(
                    delete(User).where(User.telegram_id == telegram_id)
                )
                await session.commit()
                self.logger.warning(f"Deleted user: {telegram_id}")
                return True
        except Exception as e:
            self.logger.error(f"Error deleting user {telegram_id}: {e}", exc_info=True)
            return False
    
    async def get_user_count(self) -> int:
        """
        Get total number of verified users.
        
        Returns:
            Count of verified users
        """
        try:
            async with self.db.session() as session:
                result = await session.execute(select(User))
                return len(result.scalars().all())
        except Exception as e:
            self.logger.error(f"Error getting user count: {e}", exc_info=True)
            return 0

