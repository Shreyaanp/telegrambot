"""Session service - handles verification session operations."""
import logging
import json
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete
from database import Database, VerificationSession

logger = logging.getLogger(__name__)


class SessionService:
    """Service for managing verification sessions."""
    
    def __init__(self, db: Database):
        """
        Initialize session service.
        
        Args:
            db: Database instance
        """
        self.db = db
        self.logger = logging.getLogger(__name__)
    
    async def create_session(
        self,
        session_id: str,
        telegram_id: int,
        chat_id: int,
        expires_at: datetime,
        group_id: Optional[int] = None,
        trigger_type: str = "manual",
        message_ids: Optional[List[int]] = None
    ) -> Optional[VerificationSession]:
        """
        Create a new verification session.
        
        Args:
            session_id: Mercle SDK session ID
            telegram_id: Telegram user ID
            chat_id: Chat ID where verification message was sent
            expires_at: Session expiration time
            group_id: Group ID (if triggered by group join)
            trigger_type: "auto_join" or "manual_command"
            message_ids: List of message IDs to delete later
        
        Returns:
            Created VerificationSession object or None if failed
        """
        try:
            async with self.db.session() as session:
                # Serialize message IDs to JSON
                message_ids_json = json.dumps(message_ids) if message_ids else None
                
                verification_session = VerificationSession(
                    session_id=session_id,
                    telegram_id=telegram_id,
                    chat_id=chat_id,
                    group_id=group_id,
                    expires_at=expires_at,
                    trigger_type=trigger_type,
                    message_ids=message_ids_json,
                    created_at=datetime.utcnow(),
                    status="pending"
                )
                session.add(verification_session)
                await session.commit()
                self.logger.info(f"Created verification session: {session_id}")
                return verification_session
                
        except Exception as e:
            self.logger.error(f"Error creating session {session_id}: {e}", exc_info=True)
            return None
    
    async def get_session(self, session_id: str) -> Optional[VerificationSession]:
        """
        Get a verification session by ID.
        
        Args:
            session_id: Session ID
        
        Returns:
            VerificationSession object or None if not found
        """
        try:
            async with self.db.session() as session:
                return await session.get(VerificationSession, session_id)
        except Exception as e:
            self.logger.error(f"Error getting session {session_id}: {e}", exc_info=True)
            return None
    
    async def get_active_session(self, telegram_id: int) -> Optional[VerificationSession]:
        """
        Get active (pending) session for a user.
        
        Args:
            telegram_id: Telegram user ID
        
        Returns:
            Active VerificationSession or None if not found
        """
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(VerificationSession).where(
                        VerificationSession.telegram_id == telegram_id,
                        VerificationSession.status == "pending"
                    ).order_by(VerificationSession.created_at.desc())
                )
                return result.scalar_one_or_none()
        except Exception as e:
            self.logger.error(f"Error getting active session for {telegram_id}: {e}", exc_info=True)
            return None
    
    async def update_status(self, session_id: str, status: str) -> bool:
        """
        Update session status.
        
        Args:
            session_id: Session ID
            status: New status (pending/approved/rejected/expired)
        
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            async with self.db.session() as session:
                await session.execute(
                    update(VerificationSession)
                    .where(VerificationSession.session_id == session_id)
                    .values(status=status)
                )
                await session.commit()
                self.logger.info(f"Updated session {session_id} status to {status}")
                return True
        except Exception as e:
            self.logger.error(f"Error updating session {session_id}: {e}", exc_info=True)
            return False
    
    async def store_message_ids(self, session_id: str, message_ids: List[int]) -> bool:
        """
        Store message IDs associated with a session.
        
        Args:
            session_id: Session ID
            message_ids: List of message IDs
        
        Returns:
            True if stored successfully, False otherwise
        """
        try:
            async with self.db.session() as session:
                message_ids_json = json.dumps(message_ids)
                await session.execute(
                    update(VerificationSession)
                    .where(VerificationSession.session_id == session_id)
                    .values(message_ids=message_ids_json)
                )
                await session.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error storing message IDs for {session_id}: {e}", exc_info=True)
            return False
    
    async def get_message_ids(self, session_id: str) -> List[int]:
        """
        Get message IDs associated with a session.
        
        Args:
            session_id: Session ID
        
        Returns:
            List of message IDs
        """
        try:
            session_obj = await self.get_session(session_id)
            if session_obj and session_obj.message_ids:
                return json.loads(session_obj.message_ids)
            return []
        except Exception as e:
            self.logger.error(f"Error getting message IDs for {session_id}: {e}", exc_info=True)
            return []
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Mark expired sessions as expired.
        
        Returns:
            Number of sessions marked as expired
        """
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    update(VerificationSession)
                    .where(
                        VerificationSession.status == "pending",
                        VerificationSession.expires_at < datetime.utcnow()
                    )
                    .values(status="expired")
                )
                await session.commit()
                count = result.rowcount
                if count > 0:
                    self.logger.info(f"Marked {count} sessions as expired")
                return count
        except Exception as e:
            self.logger.error(f"Error cleaning up expired sessions: {e}", exc_info=True)
            return 0
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session (use with caution!).
        
        Args:
            session_id: Session ID
        
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            async with self.db.session() as session:
                await session.execute(
                    delete(VerificationSession).where(
                        VerificationSession.session_id == session_id
                    )
                )
                await session.commit()
                self.logger.info(f"Deleted session: {session_id}")
                return True
        except Exception as e:
            self.logger.error(f"Error deleting session {session_id}: {e}", exc_info=True)
            return False
    
    async def get_pending_sessions_count(self) -> int:
        """
        Get count of pending sessions.
        
        Returns:
            Count of pending sessions
        """
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(VerificationSession).where(
                        VerificationSession.status == "pending"
                    )
                )
                return len(result.scalars().all())
        except Exception as e:
            self.logger.error(f"Error getting pending sessions count: {e}", exc_info=True)
            return 0
    
    async def get_sessions_by_group(self, group_id: int) -> List[VerificationSession]:
        """
        Get all sessions for a group.
        
        Args:
            group_id: Group ID
        
        Returns:
            List of VerificationSession objects
        """
        try:
            async with self.db.session() as session:
                result = await session.execute(
                    select(VerificationSession).where(
                        VerificationSession.group_id == group_id
                    ).order_by(VerificationSession.created_at.desc())
                )
                return result.scalars().all()
        except Exception as e:
            self.logger.error(f"Error getting sessions for group {group_id}: {e}", exc_info=True)
            return []

