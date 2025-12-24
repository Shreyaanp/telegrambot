"""User management service."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy import select, update, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, VerificationSession
from database.db import db

logger = logging.getLogger(__name__)


class UserManager:
    """Manages user verification status and database operations."""
    
    async def is_verified(self, telegram_id: int) -> bool:
        """Check if user is verified and verification hasn't expired."""
        async with db.session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return False
            # Check if verification has expired
            if user.verified_until and user.verified_until > datetime.utcnow():
                return True
            return False
    
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
    ) -> Optional[User]:
        """
        Create or update a verified user.

        Returns:
            The created/updated user, or None if the Mercle user is already linked
            to a different Telegram account (enforced by the unique constraint on
            `users.mercle_user_id`).
        """
        async with db.session() as session:
            # Guardrail: prevent linking one Mercle identity to multiple Telegram IDs.
            try:
                result = await session.execute(select(User).where(User.mercle_user_id == mercle_user_id))
                conflict_user = result.scalar_one_or_none()
                if conflict_user and int(conflict_user.telegram_id) != int(telegram_id):
                    logger.warning(
                        "Mercle identity already linked to another Telegram account; "
                        "telegram_id=%s conflicts_with=%s",
                        int(telegram_id),
                        int(conflict_user.telegram_id),
                    )
                    return None
            except Exception:
                # Best-effort: if we can't check, let the DB constraint enforce it.
                conflict_user = None

            # Check if user already exists
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            existing_user = result.scalar_one_or_none()
            
            try:
                if existing_user:
                    # Update existing user - but check if we're changing the mercle_user_id
                    # If the new mercle_user_id is different and already linked to another user,
                    # we need to reject this update
                    if existing_user.mercle_user_id != mercle_user_id:
                        # Check if the new mercle_user_id is already taken by someone else
                        result = await session.execute(
                            select(User).where(User.mercle_user_id == mercle_user_id)
                        )
                        other_user = result.scalar_one_or_none()
                        if other_user and int(other_user.telegram_id) != int(telegram_id):
                            logger.warning(
                                "Cannot update user %s: mercle_user_id %s already linked to user %s",
                                telegram_id,
                                mercle_user_id,
                                other_user.telegram_id,
                            )
                            return None
                    
                    # Safe to update
                    existing_user.mercle_user_id = mercle_user_id
                    existing_user.username = username
                    existing_user.verified_at = datetime.utcnow()
                    existing_user.verified_until = datetime.utcnow() + timedelta(days=7)
                    await session.flush()
                    logger.info(f"Updated verified user: {telegram_id} ({username}) - expires in 7 days")
                    return existing_user

                # Create new user
                now = datetime.utcnow()
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    mercle_user_id=mercle_user_id,
                    verified_at=now,
                    verified_until=now + timedelta(days=7),
                )
                session.add(user)
                await session.flush()
                logger.info(f"Created verified user: {telegram_id} ({username}) - expires in 7 days")
                return user
            except IntegrityError as e:
                # Handle race/conflict without crashing the verification flow.
                #
                # This can happen if:
                # - two pollers finish at the same time (double "approved" callback)
                # - the user verifies twice quickly
                # - the identity is already linked elsewhere (unique mercle_user_id)
                try:
                    await session.rollback()
                except Exception:
                    pass

                # If the Mercle identity is already linked, enforce that invariant.
                try:
                    result = await session.execute(select(User).where(User.mercle_user_id == mercle_user_id))
                    conflict_user = result.scalar_one_or_none()
                except Exception:
                    conflict_user = None

                if conflict_user:
                    if int(conflict_user.telegram_id) != int(telegram_id):
                        logger.warning(
                            "Mercle identity conflict on insert/update; telegram_id=%s conflicts_with=%s",
                            int(telegram_id),
                            int(conflict_user.telegram_id),
                        )
                        return None
                    # Same Telegram account won the race: treat as success.
                    conflict_user.username = username
                    conflict_user.verified_at = datetime.utcnow()
                    conflict_user.verified_until = datetime.utcnow() + timedelta(days=7)
                    return conflict_user

                # If the Telegram user row already exists (concurrent insert), treat as success.
                try:
                    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
                    existing_user = result.scalar_one_or_none()
                except Exception:
                    existing_user = None

                if existing_user:
                    existing_user.mercle_user_id = mercle_user_id
                    existing_user.username = username
                    existing_user.verified_at = datetime.utcnow()
                    existing_user.verified_until = datetime.utcnow() + timedelta(days=7)
                    return existing_user

                # Unknown IntegrityError: bubble up so we can see it in logs/metrics.
                raise e

    async def create_session(
        self,
        session_id: str,
        telegram_id: int,
        chat_id: int,
        expires_at: datetime,
        telegram_username: Optional[str] = None,
        group_id: Optional[int] = None,
        from_mini_app: bool = False
    ) -> VerificationSession:
        """Create a new verification session."""
        async with db.session() as session:
            ver_session = VerificationSession(
                session_id=session_id,
                telegram_id=telegram_id,
                chat_id=chat_id,
                telegram_username=telegram_username,
                group_id=group_id,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
                status="pending",
                from_mini_app=from_mini_app
            )
            session.add(ver_session)
            await session.commit()
            await session.refresh(ver_session)
            
            logger.info(f"Created verification session: {session_id} for user {telegram_id} from_mini_app={from_mini_app}")
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
    
    async def cleanup_expired_sessions(self) -> int:
        """Mark expired pending sessions as expired."""
        async with db.session() as session:
            result = await session.execute(
                update(VerificationSession)
                .where(
                    and_(
                        VerificationSession.status == "pending",
                        VerificationSession.expires_at < datetime.utcnow()
                    )
                )
                .values(status="expired")
            )
            await session.commit()
            count = result.rowcount
            if count > 0:
                logger.info(f"Cleaned up {count} expired sessions")
            return count
    
    async def get_user_sessions(self, telegram_id: int) -> List[VerificationSession]:
        """Get all sessions for a user."""
        async with db.session() as session:
            result = await session.execute(
                select(VerificationSession)
                .where(VerificationSession.telegram_id == telegram_id)
                .order_by(VerificationSession.created_at.desc())
            )
            return list(result.scalars().all())
    
    async def get_active_session(self, telegram_id: int) -> Optional[VerificationSession]:
        """Get active pending session for a user."""
        async with db.session() as session:
            result = await session.execute(
                select(VerificationSession)
                .where(
                    and_(
                        VerificationSession.telegram_id == telegram_id,
                        VerificationSession.status == "pending",
                        VerificationSession.expires_at > datetime.utcnow()
                    )
                )
                .order_by(VerificationSession.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
    
    async def store_message_ids(self, session_id: str, message_ids: list):
        """Store message IDs to delete later."""
        async with db.session() as session:
            result = await session.execute(
                select(VerificationSession).where(
                    VerificationSession.session_id == session_id
                )
            )
            ver_session = result.scalar_one_or_none()
            
            if ver_session:
                ver_session.message_ids = ",".join(str(mid) for mid in message_ids)
                await session.commit()
                logger.info(f"Stored message IDs for session {session_id}")
