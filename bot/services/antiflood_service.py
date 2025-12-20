"""Anti-flood service - rate limiting and spam detection."""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from sqlalchemy import select, and_

from database.db import db
from database.models import FloodTracker, Group

logger = logging.getLogger(__name__)


class AntiFloodService:
    """
    Anti-flood protection service.
    
    Tracks message rates and detects flooding/spam.
    Features:
    - Configurable message limit per minute
    - Delete all flood messages
    - Warning system before action
    - Multiple action types (mute/warn/kick/ban)
    """
    
    async def check_flood(
        self, 
        group_id: int, 
        user_id: int, 
        message_id: Optional[int] = None
    ) -> Tuple[bool, int, List[int], dict]:
        """
        Check if user is flooding and update their message count.
        
        Args:
            group_id: Group ID
            user_id: User ID
            message_id: Current message ID (to track for deletion)
            
        Returns:
            Tuple of (is_flooding, message_count, message_ids_to_delete, settings)
            - is_flooding: True if user exceeded limit
            - message_count: Current message count in window
            - message_ids_to_delete: List of message IDs to delete if flooding
            - settings: Dict with antiflood settings
        """
        async with db.session() as session:
            # Get group settings
            group_result = await session.execute(
                select(Group).where(Group.group_id == group_id)
            )
            group = group_result.scalar_one_or_none()
            
            settings = {
                "enabled": False,
                "limit": 10,
                "mute_seconds": 300,
                "action": "mute",
                "delete_messages": True,
                "warn_threshold": 0,
                "silent": False,
            }
            
            if not group:
                return False, 0, [], settings
            
            settings["enabled"] = bool(getattr(group, "antiflood_enabled", False))
            settings["limit"] = int(getattr(group, "antiflood_limit", 10) or 10)
            settings["mute_seconds"] = int(getattr(group, "antiflood_mute_seconds", 300) or 300)
            settings["action"] = str(getattr(group, "antiflood_action", "mute") or "mute")
            settings["delete_messages"] = bool(getattr(group, "antiflood_delete_messages", True))
            settings["warn_threshold"] = int(getattr(group, "antiflood_warn_threshold", 0) or 0)
            settings["silent"] = bool(getattr(group, "silent_automations", False))
            
            if not settings["enabled"]:
                return False, 0, [], settings
            
            limit = settings["limit"]
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
            
            now = datetime.utcnow()
            
            if not tracker:
                # Create new tracker
                message_ids = [message_id] if message_id else []
                tracker = FloodTracker(
                    group_id=group_id,
                    telegram_id=user_id,
                    message_count=1,
                    window_start=now,
                    last_message=now,
                    message_ids=json.dumps(message_ids),
                    warning_count=0
                )
                session.add(tracker)
                await session.commit()
                return False, 1, [], settings
            
            # Check if window expired
            if (now - tracker.window_start).total_seconds() > window:
                # Reset window
                message_ids = [message_id] if message_id else []
                tracker.message_count = 1
                tracker.window_start = now
                tracker.last_message = now
                tracker.message_ids = json.dumps(message_ids)
                tracker.warning_count = 0
                await session.commit()
                return False, 1, [], settings
            
            # Parse existing message IDs
            try:
                existing_ids = json.loads(tracker.message_ids or "[]")
            except (json.JSONDecodeError, TypeError):
                existing_ids = []
            
            # Add current message ID
            if message_id and message_id not in existing_ids:
                existing_ids.append(message_id)
            
            # Increment count
            tracker.message_count += 1
            tracker.last_message = now
            tracker.message_ids = json.dumps(existing_ids)
            
            # Check if flooding
            is_flooding = tracker.message_count > limit
            
            message_ids_to_delete = []
            
            if is_flooding:
                logger.warning(
                    f"Flood detected: User {user_id} in group {group_id} "
                    f"({tracker.message_count} messages in {window}s, limit={limit})"
                )
                
                # Return all message IDs for deletion
                if settings["delete_messages"]:
                    message_ids_to_delete = existing_ids.copy()
                
                # Increment warning count
                tracker.warning_count += 1
            
            await session.commit()
            
            return is_flooding, tracker.message_count, message_ids_to_delete, settings
    
    async def get_warning_count(self, group_id: int, user_id: int) -> int:
        """Get current warning count for user in flood window."""
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
            return tracker.warning_count if tracker else 0
    
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
    
    async def clear_message_ids(self, group_id: int, user_id: int):
        """Clear tracked message IDs after deletion."""
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
                tracker.message_ids = json.dumps([])
                await session.commit()
