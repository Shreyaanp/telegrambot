"""Rules plugin - group rules management."""
import logging
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ChatType

from bot.plugins.base import BasePlugin
from bot.services import GroupService, PermissionService

logger = logging.getLogger(__name__)


class RulesPlugin(BasePlugin):
    """Plugin for managing group rules."""
    
    @property
    def name(self) -> str:
        return "rules"
    
    @property
    def description(self) -> str:
        return "Group rules management"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        self.group_service = GroupService(db)
        self.permission_service = PermissionService(db)
    
    async def on_load(self):
        """Register handlers when plugin is loaded."""
        await super().on_load()
        
        self.router.message.register(self.cmd_rules, Command("rules"))
        self.router.message.register(self.cmd_setrules, Command("setrules"))
        
        self.logger.info("Rules plugin loaded successfully")
    
    def get_commands(self):
        return [
            {"command": "/rules", "description": "Show group rules"},
            {"command": "/setrules", "description": "Set group rules (admin only)"},
        ]
    
    async def cmd_rules(self, message: Message):
        """Show group rules."""
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await message.answer("⚠️ This command can only be used in groups.")
            return
        
        group = await self.group_service.get_group(message.chat.id)
        
        if not group or not group.rules_text:
            await message.answer("📋 No rules have been set for this group.")
            return
        
        await message.answer(f"📋 **Group Rules:**\n\n{group.rules_text}")
    
    async def cmd_setrules(self, message: Message):
        """Set group rules."""
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await message.answer("⚠️ This command can only be used in groups.")
            return
        
        # Check permission
        if not await self.permission_service.is_admin(self.bot, message.chat.id, message.from_user.id):
            await message.answer("⚠️ Only admins can set rules.")
            return
        
        # Extract rules text
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("❌ Usage: `/setrules <rules text>`")
            return
        
        rules_text = parts[1]
        group_id = message.chat.id
        
        await self.group_service.set_rules(group_id, rules_text)
        await message.answer(f"✅ Rules updated:\n\n{rules_text}")

