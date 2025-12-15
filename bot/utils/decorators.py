"""Decorators for command handlers."""
import logging
from functools import wraps
from aiogram.types import Message
from aiogram.enums import ChatType

logger = logging.getLogger(__name__)


def group_only():
    """Decorator to restrict command to group chats only."""
    def decorator(handler):
        @wraps(handler)
        async def wrapper(self, message: Message, *args, **kwargs):
            if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
                await message.answer("⚠️ This command can only be used in groups.")
                return
            return await handler(self, message, *args, **kwargs)
        return wrapper
    return decorator


def dm_only():
    """Decorator to restrict command to private chats only."""
    def decorator(handler):
        @wraps(handler)
        async def wrapper(self, message: Message, *args, **kwargs):
            if message.chat.type != ChatType.PRIVATE:
                await message.answer("⚠️ This command can only be used in private messages.")
                return
            return await handler(self, message, *args, **kwargs)
        return wrapper
    return decorator


def admin_only(permission_service, action: str = None):
    """
    Decorator to check if user is admin (Telegram admin OR has custom permission).
    
    Args:
        permission_service: PermissionService instance
        action: Specific action to check (verify, kick, ban, warn, settings)
    """
    def decorator(handler):
        @wraps(handler)
        async def wrapper(self, message: Message, *args, **kwargs):
            # Must be in a group
            if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
                await message.answer("⚠️ This command can only be used in groups.")
                return
            
            user_id = message.from_user.id
            group_id = message.chat.id
            bot = self.bot
            
            # Check if user can perform the action
            if action:
                can_perform = await permission_service.can_perform_action(
                    bot, group_id, user_id, action
                )
            else:
                can_perform = await permission_service.is_admin(bot, group_id, user_id)
            
            if not can_perform:
                await message.answer("⚠️ You don't have permission to use this command.")
                return
            
            return await handler(self, message, *args, **kwargs)
        return wrapper
    return decorator

