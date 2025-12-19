"""Anti-flood service - rate limiting and spam detection."""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_

from database.db import db
from database.models import FloodTracker, Group

logger = logging.getLogger(__name__)


class AntiFloodService:
    """
    Anti-flood protection service.
    
    Tracks message rates and detects flooding/spam.
    """
    
    async def check_flood(self, group_id: int, user_id: int) -> tuple[bool, int]:
        """
        Check if user is flooding and update their message count.
        
        Args:
            group_id: Group ID
            user_id: User ID
            
        Returns:
            Tuple of (is_flooding, message_count)
        """
        async with db.session() as session:
            # Get group settings
            group_result = await session.execute(
                select(Group).where(Group.group_id == group_id)
            )
            group = group_result.scalar_one_or_none()
            
            if not group or not group.antiflood_enabled:
                return False, 0
            
            limit = group.antiflood_limit or 10
            window = 60  # 1 minute window
            
            # Get or create flood tracker
            result = await session.execute(
                select(FloodTracker)
                .where(
                    and_(
                        FloodTracker.group_id == group_id,
                        FloodTracker.telegram_id == user_id
                    )
                )
            )
            tracker = result.scalar_one_or_none()
            
            now = datetime.now(timezone.utc)
            
            if not tracker:
                # Create new tracker
                tracker = FloodTracker(
                    group_id=group_id,
                    telegram_id=user_id,
                    message_count=1,
                    window_start=now,
                    last_message=now
                )
                session.add(tracker)
                await session.commit()
                return False, 1
            
            # Check if window expired
            if (now - tracker.window_start).total_seconds() > window:
                # Reset window
                tracker.message_count = 1
                tracker.window_start = now
                tracker.last_message = now
                await session.commit()
                return False, 1
            
            # Increment count
            tracker.message_count += 1
            tracker.last_message = now
            await session.commit()
            
            # Check if flooding
            is_flooding = tracker.message_count > limit
            
            if is_flooding:
                logger.warning(
                    f"Flood detected: User {user_id} in group {group_id} "
                    f"({tracker.message_count} messages in {window}s)"
                )
            
            return is_flooding, tracker.message_count
    
    async def reset_flood(self, group_id: int, user_id: int):
        """
        Reset flood tracking for a user.
        
        Args:
            group_id: Group ID
            user_id: User ID
        """
        async with db.session() as session:
            result = await session.execute(
                select(FloodTracker)
                .where(
                    and_(
                        FloodTracker.group_id == group_id,
                        FloodTracker.telegram_id == user_id
                    )
                )
            )
            tracker = result.scalar_one_or_none()
            
            if tracker:
                await session.delete(tracker)
                await session.commit()
                logger.info(f"Reset flood tracking for user {user_id} in group {group_id}")

