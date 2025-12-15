"""Message cleaner service - handles batch message deletion."""
import logging
import asyncio
from typing import List
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)


class MessageCleanerService:
    """Service for cleaning up bot messages."""
    
    def __init__(self):
        """Initialize message cleaner service."""
        self.logger = logging.getLogger(__name__)
    
    async def delete_message(self, bot: Bot, chat_id: int, message_id: int) -> bool:
        """
        Delete a single message.
        
        Args:
            bot: Bot instance
            chat_id: Chat ID
            message_id: Message ID
        
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            return True
        except TelegramBadRequest as e:
            if "message to delete not found" in str(e).lower():
                self.logger.debug(f"Message {message_id} already deleted in chat {chat_id}")
            else:
                self.logger.warning(f"Failed to delete message {message_id} in chat {chat_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error deleting message {message_id} in chat {chat_id}: {e}")
            return False
    
    async def delete_messages(
        self,
        bot: Bot,
        chat_id: int,
        message_ids: List[int],
        delay: float = 0.1
    ) -> int:
        """
        Delete multiple messages.
        
        Args:
            bot: Bot instance
            chat_id: Chat ID
            message_ids: List of message IDs to delete
            delay: Delay between deletions (to avoid rate limits)
        
        Returns:
            Number of messages successfully deleted
        """
        if not message_ids:
            return 0
        
        deleted_count = 0
        for message_id in message_ids:
            if await self.delete_message(bot, chat_id, message_id):
                deleted_count += 1
            
            # Small delay to avoid rate limits
            if delay > 0:
                await asyncio.sleep(delay)
        
        self.logger.info(f"Deleted {deleted_count}/{len(message_ids)} messages in chat {chat_id}")
        return deleted_count
    
    async def delete_messages_after_delay(
        self,
        bot: Bot,
        chat_id: int,
        message_ids: List[int],
        delay_seconds: int
    ):
        """
        Delete messages after a specified delay.
        
        Args:
            bot: Bot instance
            chat_id: Chat ID
            message_ids: List of message IDs to delete
            delay_seconds: Delay in seconds before deletion
        """
        await asyncio.sleep(delay_seconds)
        await self.delete_messages(bot, chat_id, message_ids)

