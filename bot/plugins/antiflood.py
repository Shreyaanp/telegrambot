"""Anti-flood plugin - message rate limiting."""
import logging
from datetime import datetime, timedelta
from aiogram.types import Message
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select, update, delete

from bot.plugins.base import BasePlugin
from database import FloodTracker

logger = logging.getLogger(__name__)


class AntiFloodPlugin(BasePlugin):
    """Plugin for anti-flood protection."""
    
    @property
    def name(self) -> str:
        return "antiflood"
    
    @property
    def description(self) -> str:
        return "Anti-flood protection with rate limiting"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        self.max_messages = 10  # Max messages in window
        self.window_seconds = 10  # Time window in seconds
    
    async def on_load(self):
        """Register handlers when plugin is loaded."""
        await super().on_load()
        
        # Register message handler (runs for all messages)
        self.router.message.register(self.check_flood)
        
        self.logger.info("Anti-flood plugin loaded successfully")
    
    def get_commands(self):
        return []  # No commands, runs automatically
    
    async def check_flood(self, message: Message):
        """Check if user is flooding."""
        # Only in groups
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            return
        
        group_id = message.chat.id
        user_id = message.from_user.id
        
        try:
            async with self.db.session() as session:
                # Get or create flood tracker
                result = await session.execute(
                    select(FloodTracker).where(
                        FloodTracker.group_id == group_id,
                        FloodTracker.telegram_id == user_id
                    )
                )
                tracker = result.scalar_one_or_none()
                
                now = datetime.utcnow()
                
                if not tracker:
                    # Create new tracker
                    tracker = FloodTracker(
                        group_id=group_id,
                        telegram_id=user_id,
                        message_count=1,
                        window_start=now
                    )
                    session.add(tracker)
                    await session.commit()
                    return
                
                # Check if window has expired
                if now - tracker.window_start > timedelta(seconds=self.window_seconds):
                    # Reset window
                    tracker.message_count = 1
                    tracker.window_start = now
                    await session.commit()
                    return
                
                # Increment counter
                tracker.message_count += 1
                await session.commit()
                
                # Check if flooding
                if tracker.message_count > self.max_messages:
                    # Mute user for 5 minutes
                    try:
                        await self.bot.restrict_chat_member(
                            chat_id=group_id,
                            user_id=user_id,
                            permissions={"can_send_messages": False},
                            until_date=datetime.utcnow() + timedelta(minutes=5)
                        )
                        await message.answer(
                            f"⚠️ User `{user_id}` has been muted for 5 minutes due to flooding."
                        )
                        self.logger.info(f"Muted user {user_id} in group {group_id} for flooding")
                        
                        # Reset tracker
                        tracker.message_count = 0
                        tracker.window_start = now
                        await session.commit()
                        
                    except TelegramBadRequest as e:
                        self.logger.error(f"Failed to mute user {user_id}: {e}")
                
        except Exception as e:
            self.logger.error(f"Error in flood check: {e}", exc_info=True)

