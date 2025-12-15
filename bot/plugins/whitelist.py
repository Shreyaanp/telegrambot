"""Whitelist plugin - bypass verification for trusted users."""
import logging
from typing import Optional
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ChatType

from bot.plugins.base import BasePlugin
from bot.services import PermissionService

logger = logging.getLogger(__name__)


class WhitelistPlugin(BasePlugin):
    """Plugin for whitelist management."""
    
    @property
    def name(self) -> str:
        return "whitelist"
    
    @property
    def description(self) -> str:
        return "Whitelist management for bypassing verification"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        self.permission_service = PermissionService(db)
    
    async def on_load(self):
        """Register handlers when plugin is loaded."""
        await super().on_load()
        
        self.router.message.register(self.cmd_whitelist, Command("whitelist"))
        
        self.logger.info("Whitelist plugin loaded successfully")
    
    def get_commands(self):
        return [
            {"command": "/whitelist", "description": "Manage whitelist (add/remove/list)"},
        ]
    
    def _extract_user_id(self, message: Message) -> Optional[int]:
        """Extract user ID from message."""
        if message.reply_to_message:
            return message.reply_to_message.from_user.id
        if message.text:
            parts = message.text.split()
            if len(parts) >= 3 and parts[2].isdigit():
                return int(parts[2])
        return None
    
    async def cmd_whitelist(self, message: Message):
        """
        Manage whitelist.
        
        Usage:
            /whitelist list - Show whitelisted users
            /whitelist add <user_id> [reason] - Add to whitelist
            /whitelist remove <user_id> - Remove from whitelist
        """
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await message.answer("⚠️ This command can only be used in groups.")
            return
        
        # Check permission
        if not await self.permission_service.is_admin(self.bot, message.chat.id, message.from_user.id):
            await message.answer("⚠️ Only admins can manage the whitelist.")
            return
        
        parts = message.text.split(maxsplit=3)
        
        if len(parts) < 2:
            await message.answer(
                "❌ **Usage:**\n"
                "`/whitelist list` - Show whitelisted users\n"
                "`/whitelist add <user_id> [reason]` - Add to whitelist\n"
                "`/whitelist remove <user_id>` - Remove from whitelist"
            )
            return
        
        action = parts[1].lower()
        group_id = message.chat.id
        
        if action == "list":
            whitelist = await self.permission_service.get_whitelist(group_id)
            if not whitelist:
                await message.answer("📋 Whitelist is empty.")
                return
            
            text = "📋 **Whitelisted Users:**\n\n"
            for entry in whitelist:
                text += f"• User `{entry.telegram_id}`"
                if entry.reason:
                    text += f" - {entry.reason}"
                text += "\n"
            
            await message.answer(text)
        
        elif action == "add":
            target_user_id = self._extract_user_id(message)
            if not target_user_id:
                await message.answer("❌ Reply to a user's message or use `/whitelist add <user_id> [reason]`")
                return
            
            reason = parts[3] if len(parts) > 3 else "No reason provided"
            admin_id = message.from_user.id
            
            await self.permission_service.add_to_whitelist(group_id, target_user_id, admin_id, reason)
            await message.answer(f"✅ User `{target_user_id}` added to whitelist.")
        
        elif action == "remove":
            target_user_id = self._extract_user_id(message)
            if not target_user_id:
                await message.answer("❌ Use `/whitelist remove <user_id>`")
                return
            
            await self.permission_service.remove_from_whitelist(group_id, target_user_id)
            await message.answer(f"✅ User `{target_user_id}` removed from whitelist.")
        
        else:
            await message.answer("❌ Unknown action. Use `list`, `add`, or `remove`.")

