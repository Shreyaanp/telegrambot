"""Permission checking utilities - make admin checks easy and clear."""
import logging
from typing import Optional
from functools import wraps
from aiogram.types import Message, CallbackQuery
from aiogram import Bot
from database.db import db
from database.models import Permission, GroupUserState
from sqlalchemy import select

logger = logging.getLogger(__name__)

async def can_user(bot: Bot, chat_id: int, user_id: int, action: str) -> bool:
    """
    Unified permission check: Telegram admin OR matching custom role permission.

    action: one of:
      - 'verify', 'kick', 'ban', 'warn', 'filters', 'notes'
      - 'settings', 'locks', 'roles', 'status', 'logs'
    """
    if await is_user_admin(bot, chat_id, user_id):
        return True
    return await has_role_permission(chat_id, user_id, action)


async def is_user_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """
    Check if user is a Telegram admin in the chat.
    
    Args:
        bot: Bot instance
        chat_id: Chat/group ID
        user_id: User's Telegram ID
        
    Returns:
        True if user is admin, False otherwise
    """
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["creator", "administrator"]
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False


async def is_bot_admin(bot: Bot, chat_id: int) -> bool:
    """
    Check if the bot itself is an admin in the chat.
    
    Args:
        bot: Bot instance
        chat_id: Chat/group ID
        
    Returns:
        True if bot is admin, False otherwise
    """
    try:
        bot_info = await bot.get_me()
        member = await bot.get_chat_member(chat_id, bot_info.id)
        return member.status in ["administrator"]
    except Exception as e:
        logger.error(f"Error checking bot admin status: {e}")
        return False


async def can_restrict_members(bot: Bot, chat_id: int, user_id: int) -> bool:
    """
    Check if user has permission to restrict members (kick, ban, mute).
    
    Args:
        bot: Bot instance
        chat_id: Chat/group ID
        user_id: User's Telegram ID
        
    Returns:
        True if user can restrict members, False otherwise
    """
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status == "creator":
            return True
        if member.status == "administrator":
            return member.can_restrict_members
        return False
    except Exception as e:
        logger.error(f"Error checking restrict permission: {e}")
        return False


async def has_role_permission(chat_id: int, user_id: int, action: str) -> bool:
    """
    Check custom role permissions stored in DB for this group/user.
    
    action: one of:
      - 'verify', 'kick', 'ban', 'warn', 'filters', 'notes'
      - 'settings', 'locks', 'roles', 'status', 'logs'
    """
    try:
        async with db.session() as session:
            result = await session.execute(
                select(Permission).where(
                    Permission.group_id == chat_id,
                    Permission.telegram_id == user_id
                )
            )
            perm = result.scalar_one_or_none()
            if not perm:
                return False
            if action == "verify":
                return perm.can_verify
            if action in ("kick", "mute", "unmute", "purge"):
                return perm.can_kick
            if action in ("ban", "unban"):
                return perm.can_ban
            if action == "warn":
                return perm.can_warn
            if action == "filters":
                return perm.can_manage_filters
            if action == "notes":
                return perm.can_manage_notes
            if action == "settings":
                return getattr(perm, "can_manage_settings", False)
            if action == "locks":
                return getattr(perm, "can_manage_locks", False)
            if action == "roles":
                return getattr(perm, "can_manage_roles", False)
            if action == "status":
                return getattr(perm, "can_view_status", False)
            if action == "logs":
                return getattr(perm, "can_view_logs", False)
            return False
    except Exception as e:
        logger.error(f"Error checking role permission: {e}")
        return False


async def can_delete_messages(bot: Bot, chat_id: int, user_id: int) -> bool:
    """
    Check if user has permission to delete messages.
    
    Args:
        bot: Bot instance
        chat_id: Chat/group ID
        user_id: User's Telegram ID
        
    Returns:
        True if user can delete messages, False otherwise
    """
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status == "creator":
            return True
        if member.status == "administrator":
            return member.can_delete_messages
        return False
    except Exception as e:
        logger.error(f"Error checking delete permission: {e}")
        return False


async def can_pin_messages(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Check if user can pin messages."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status == "creator":
            return True
        if member.status == "administrator":
            return getattr(member, "can_pin_messages", False)
        return False
    except Exception as e:
        logger.error(f"Error checking pin permission: {e}")
        return False


async def get_user_mention(message: Message, user_id: Optional[int] = None) -> str:
    """
    Get a mention string for a user.
    
    Args:
        message: Message object
        user_id: Optional user ID (if not provided, uses message sender)
        
    Returns:
        Mention string like "@username" or "User"
    """
    if user_id is None:
        user_id = message.from_user.id
    
    # Try to get from message entities
    if message.reply_to_message and message.reply_to_message.from_user.id == user_id:
        user = message.reply_to_message.from_user
        if user.username:
            return f"@{user.username}"
        return user.first_name or "User"
    
    # Try to get from message sender
    if message.from_user.id == user_id:
        if message.from_user.username:
            return f"@{message.from_user.username}"
        return message.from_user.first_name or "User"
    
    return f"User {user_id}"


def require_admin(func):
    """
    Decorator to require admin permissions.
    
    Usage:
        @require_admin
        async def cmd_kick(message: Message):
            ...
    """
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        # Check if in group
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply("❌ This command only works in groups.")
            return
        
        # Telegram admins only (roles are handled by capability-specific decorators).
        if not await is_user_admin(message.bot, message.chat.id, message.from_user.id):
            await message.reply("❌ You need to be an admin to use this command.")
            return
        
        # Check if bot is admin
        if not await is_bot_admin(message.bot, message.chat.id):
            await message.reply("❌ I need to be an admin to do this.")
            return
        
        return await func(message, *args, **kwargs)
    
    return wrapper


def require_role_or_admin(action: str):
    """
    Decorator to require Telegram admin OR a matching custom role permission.
    """

    def deco(func):
        @wraps(func)
        async def wrapper(message: Message, *args, **kwargs):
            if message.chat.type not in ["group", "supergroup"]:
                await message.reply("❌ This command only works in groups.")
                return
            if not await is_user_admin(message.bot, message.chat.id, message.from_user.id):
                if not await has_role_permission(message.chat.id, message.from_user.id, action):
                    await message.reply("❌ Not allowed.")
                    return
            if not await is_bot_admin(message.bot, message.chat.id):
                await message.reply("❌ I need to be an admin to do this.")
                return
            return await func(message, *args, **kwargs)

        return wrapper

    return deco


def require_restrict_permission(func=None, *, action: str = "kick"):
    """
    Decorator to require restrict members permission.
    
    Usage:
        @require_restrict_permission
        async def cmd_kick(message: Message):
            ...
    """
    if func is None:
        def _deco(f):
            return require_restrict_permission(f, action=action)
        return _deco

    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply("❌ This command only works in groups.")
            return

        if not await can_restrict_members(message.bot, message.chat.id, message.from_user.id):
            if not await has_role_permission(message.chat.id, message.from_user.id, action):
                await message.reply("❌ Not allowed.")
                return

        if not await is_bot_admin(message.bot, message.chat.id):
            await message.reply("❌ I need to be an admin to do this.")
            return

        return await func(message, *args, **kwargs)

    return wrapper


def require_telegram_admin(func):
    """
    Decorator to require Telegram group admin (creator/administrator).
    Used for sensitive bot-local operations like granting roles.
    """
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply("❌ This command only works in groups.")
            return
        if not await is_user_admin(message.bot, message.chat.id, message.from_user.id):
            await message.reply("❌ Admins only.")
            return
        return await func(message, *args, **kwargs)
    return wrapper


async def extract_user_and_reason(message: Message) -> tuple[Optional[int], Optional[str]]:
    """
    Extract user ID and reason from a command message.
    
    Supports:
    - Reply to message: /kick [reason]
    - Mention: /kick @username [reason]
    - ID: /kick 123456 [reason]
    
    Args:
        message: Command message
        
    Returns:
        Tuple of (user_id, reason) or (None, None) if not found
    """
    user_id = None
    reason = None
    
    # Check if replying to a message
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        # Rest of command is reason
        parts = message.text.split(maxsplit=1)
        reason = parts[1] if len(parts) > 1 else None
        return user_id, reason
    
    # Parse command arguments
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        return None, None
    
    # parts[0] is command, parts[1] is user, parts[2] is reason (if exists)
    user_arg = parts[1]
    reason = parts[2] if len(parts) > 2 else None
    
    # Check if it's a mention by username
    if user_arg.startswith("@"):
        username = user_arg.lstrip("@").lower()
        # Try to resolve via admin list (limited to admins)
        try:
            admins = await message.bot.get_chat_administrators(message.chat.id)
            for adm in admins:
                if adm.user.username and adm.user.username.lower() == username:
                    return adm.user.id, reason
        except Exception as e:
            logger.warning(f"Could not fetch admins to resolve username @{username}: {e}")
        # Try to resolve via stored per-group mapping (works for silent users we saw join or verify).
        try:
            async with db.session() as session:
                result = await session.execute(
                    select(GroupUserState.telegram_id).where(
                        GroupUserState.group_id == message.chat.id,
                        GroupUserState.username_lc == username,
                    )
                )
                mapped = result.scalar_one_or_none()
                if mapped:
                    return int(mapped), reason
        except Exception as e:
            logger.debug(f"GroupUserState lookup failed for @{username}: {e}")
        # Optional: try getChat if bot has dialog with the user (best effort)
        try:
            chat_obj = await message.bot.get_chat(username)
            if chat_obj and chat_obj.id:
                return chat_obj.id, reason
        except Exception as e:
            logger.debug(f"get_chat fallback failed for @{username}: {e}")
        # Cannot reliably resolve non-admin usernames without a reply or ID
        return None, reason
    
    # Check if it's a user ID
    try:
        user_id = int(user_arg)
        return user_id, reason
    except ValueError:
        pass
    
    # Check for text mentions in entities
    if message.entities:
        for entity in message.entities:
            if entity.type == "text_mention":
                user_id = entity.user.id
                return user_id, reason
    
    return None, None


def format_time_delta(seconds: int) -> str:
    """
    Format seconds into human-readable time.
    
    Args:
        seconds: Number of seconds
        
    Returns:
        Formatted string like "5 minutes" or "2 hours"
    """
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    else:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"
