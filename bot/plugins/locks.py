"""Message locks plugin for restricting message types."""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from bot.plugins.base import BasePlugin
from bot.services.group_service import GroupService
from bot.services.permission_service import PermissionService
from database.models import Base
from sqlalchemy import Column, Integer, String, Boolean
from datetime import datetime


class MessageLock(Base):
    """Message locks table."""
    __tablename__ = "locks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False, index=True)
    lock_type = Column(String, nullable=False)  # links, media, stickers, forwards
    enabled = Column(Boolean, default=True)


class LocksPlugin(BasePlugin):
    """Plugin for locking message types."""
    
    @property
    def name(self) -> str:
        return "locks"
    
    @property
    def description(self) -> str:
        return "Lock specific message types (links, media, stickers, forwards)"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        self.group_service = GroupService(db)
        self.permission_service = PermissionService(db)
    
    async def on_load(self):
        """Register all handlers for this plugin."""
        await super().on_load()
        self.router.message.register(self.cmd_lock, Command("lock"))
        self.router.message.register(self.cmd_unlock, Command("unlock"))
        self.router.message.register(self.cmd_locks, Command("locks"))
        self.router.message.register(self.on_message, F.text | F.photo | F.video | F.document | F.sticker)
    
    def get_commands(self) -> list:
        return [
            {"command": "/lock", "description": "Lock a message type"},
            {"command": "/unlock", "description": "Unlock a message type"},
            {"command": "/locks", "description": "Show current locks"},
        ]
    
    # Commands
    
    async def cmd_lock(self, message: Message):
        """Lock a message type."""
        # Check if in group
        if message.chat.type not in ["group", "supergroup"]:
            await message.answer("❌ This command can only be used in groups.")
            return
        
        # Check if user is admin
        is_admin = await self.permission_service.is_admin(message.chat.id, message.from_user.id)
        if not is_admin:
            from bot.utils.messages import permission_denied_message
            await message.answer(permission_denied_message())
            return
        
        # Parse arguments
        args = message.text.split()
        if len(args) < 2:
            await message.answer(
                "❌ **Invalid Usage**\n\n"
                "**Usage:** `/lock <type>`\n\n"
                "**Available types:**\n"
                "• `links` - Delete all links\n"
                "• `media` - Delete all media (photos, videos, files)\n"
                "• `stickers` - Delete all stickers\n"
                "• `forwards` - Delete forwarded messages\n\n"
                "**Example:**\n"
                "`/lock links`"
            )
            return
        
        lock_type = args[1].lower()
        valid_types = ["links", "media", "stickers", "forwards"]
        
        if lock_type not in valid_types:
            await message.answer(
                f"❌ Invalid lock type: `{lock_type}`\n\n"
                f"Valid types: {', '.join(valid_types)}"
            )
            return
        
        # Save to database
        async with self.db.session() as session:
            from sqlalchemy import select
            stmt = select(MessageLock).where(
                MessageLock.group_id == message.chat.id,
                MessageLock.lock_type == lock_type
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.enabled = True
            else:
                new_lock = MessageLock(
                    group_id=message.chat.id,
                    lock_type=lock_type,
                    enabled=True
                )
                session.add(new_lock)
            
            await session.commit()
        
        lock_emoji = {
            "links": "🔗",
            "media": "📷",
            "stickers": "🎨",
            "forwards": "↗️"
        }
        
        await message.answer(
            f"🔒 **Lock Enabled**\n\n"
            f"{lock_emoji.get(lock_type, '🔒')} **{lock_type.capitalize()}** are now locked.\n\n"
            f"All {lock_type} will be automatically deleted."
        )
    
    async def cmd_unlock(self, message: Message):
        """Unlock a message type."""
        # Check if in group
        if message.chat.type not in ["group", "supergroup"]:
            await message.answer("❌ This command can only be used in groups.")
            return
        
        # Check if user is admin
        is_admin = await self.permission_service.is_admin(message.chat.id, message.from_user.id)
        if not is_admin:
            from bot.utils.messages import permission_denied_message
            await message.answer(permission_denied_message())
            return
        
        # Parse arguments
        args = message.text.split()
        if len(args) < 2:
            await message.answer(
                "❌ **Invalid Usage**\n\n"
                "**Usage:** `/unlock <type>`\n\n"
                "**Example:**\n"
                "`/unlock links`"
            )
            return
        
        lock_type = args[1].lower()
        
        # Update database
        async with self.db.session() as session:
            from sqlalchemy import select
            stmt = select(MessageLock).where(
                MessageLock.group_id == message.chat.id,
                MessageLock.lock_type == lock_type
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.enabled = False
                await session.commit()
        
        await message.answer(
            f"🔓 **Lock Disabled**\n\n"
            f"**{lock_type.capitalize()}** are now unlocked."
        )
    
    async def cmd_locks(self, message: Message):
        """Show current locks."""
        # Check if in group
        if message.chat.type not in ["group", "supergroup"]:
            await message.answer("❌ This command can only be used in groups.")
            return
        
        # Get all locks for this group
        async with self.db.session() as session:
            from sqlalchemy import select
            stmt = select(MessageLock).where(
                MessageLock.group_id == message.chat.id,
                MessageLock.enabled == True
            )
            result = await session.execute(stmt)
            locks = result.scalars().all()
        
        if not locks:
            await message.answer(
                "🔓 **No Active Locks**\n\n"
                "All message types are allowed.\n\n"
                "Use `/lock <type>` to lock a message type."
            )
            return
        
        lock_emoji = {
            "links": "🔗",
            "media": "📷",
            "stickers": "🎨",
            "forwards": "↗️"
        }
        
        lock_list = []
        for lock in locks:
            emoji = lock_emoji.get(lock.lock_type, "🔒")
            lock_list.append(f"{emoji} {lock.lock_type.capitalize()}")
        
        await message.answer(
            f"🔒 **Active Locks ({len(locks)})**\n\n"
            + "\n".join(lock_list) +
            "\n\n**Usage:**\n"
            "`/unlock <type>` - Remove a lock"
        )
    
    # Event Handlers
    
    async def on_message(self, message: Message):
        """Check if message violates any locks."""
        # Only in groups
        if message.chat.type not in ["group", "supergroup"]:
            return
        
        # Don't check admin messages
        is_admin = await self.permission_service.is_admin(message.chat.id, message.from_user.id)
        if is_admin:
            return
        
        # Get locks for this group
        async with self.db.session() as session:
            from sqlalchemy import select
            stmt = select(MessageLock).where(
                MessageLock.group_id == message.chat.id,
                MessageLock.enabled == True
            )
            result = await session.execute(stmt)
            locks = result.scalars().all()
        
        if not locks:
            return
        
        # Check each lock type
        lock_types = {lock.lock_type for lock in locks}
        should_delete = False
        violation_type = None
        
        # Check for links
        if "links" in lock_types and message.text:
            if "http://" in message.text.lower() or "https://" in message.text.lower() or "www." in message.text.lower():
                should_delete = True
                violation_type = "links"
        
        # Check for media
        if "media" in lock_types:
            if message.photo or message.video or message.document or message.audio or message.voice:
                should_delete = True
                violation_type = "media"
        
        # Check for stickers
        if "stickers" in lock_types and message.sticker:
            should_delete = True
            violation_type = "stickers"
        
        # Check for forwards
        if "forwards" in lock_types and message.forward_date:
            should_delete = True
            violation_type = "forwards"
        
        # Delete if violates lock
        if should_delete:
            try:
                await message.delete()
                self.logger.info(
                    f"Deleted message from {message.from_user.id} in {message.chat.id} "
                    f"(violated {violation_type} lock)"
                )
            except TelegramBadRequest as e:
                self.logger.error(f"Failed to delete message: {e}")

