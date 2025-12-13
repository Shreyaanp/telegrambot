"""User management service."""
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, VerificationSession
from database.db import db

logger = logging.getLogger(__name__)


class UserManager:
    """Manages user verification status and database operations."""
    
    async def is_verified(self, telegram_id: int) -> bool:
        """Check if user is verified."""
        async with db.session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            return user is not None
    
    async def get_user(self, telegram_id: int) -> Optional[User]:
        """Get user by telegram ID."""
        async with db.session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()
    
    async def create_user(
        self,
        telegram_id: int,
        mercle_user_id: str,
        username: Optional[str] = None
    ) -> User:
        """Create a new verified user."""
        async with db.session() as session:
            user = User(
                telegram_id=telegram_id,
                username=username,
                mercle_user_id=mercle_user_id,
                verified_at=datetime.utcnow()
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            logger.info(f"Created verified user: {telegram_id} ({username})")
            return user
    
    async def create_session(
        self,
        session_id: str,
        telegram_id: int,
        expires_at: datetime,
        telegram_username: Optional[str] = None,
        group_id: Optional[int] = None
    ) -> VerificationSession:
        """Create a new verification session."""
        async with db.session() as session:
            ver_session = VerificationSession(
                session_id=session_id,
                telegram_id=telegram_id,
                telegram_username=telegram_username,
                group_id=group_id,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
                status="pending"
            )
            session.add(ver_session)
            await session.commit()
            await session.refresh(ver_session)
            
            logger.info(f"Created verification session: {session_id} for user {telegram_id}")
            return ver_session
    
    async def get_session(self, session_id: str) -> Optional[VerificationSession]:
        """Get verification session by ID."""
        async with db.session() as session:
            result = await session.execute(
                select(VerificationSession).where(
                    VerificationSession.session_id == session_id
                )
            )
            return result.scalar_one_or_none()
    
    async def update_session_status(self, session_id: str, status: str):
        """Update verification session status."""
        async with db.session() as session:
            result = await session.execute(
                select(VerificationSession).where(
                    VerificationSession.session_id == session_id
                )
            )
            ver_session = result.scalar_one_or_none()
            
            if ver_session:
                ver_session.status = status
                await session.commit()
                logger.info(f"Updated session {session_id} status to: {status}")

