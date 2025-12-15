"""Warning system plugin - progressive moderation."""
import logging
from typing import Optional
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest

from bot.plugins.base import BasePlugin
from bot.services import PermissionService

logger = logging.getLogger(__name__)


class WarningsPlugin(BasePlugin):
    """Plugin for warning system and progressive moderation."""
    
    @property
    def name(self) -> str:
        return "warnings"
    
    @property
    def description(self) -> str:
        return "Warning system with auto-kick at 3 warnings"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        self.permission_service = PermissionService(db)
        self.max_warnings = 3  # Configurable
    
    async def on_load(self):
        """Register handlers when plugin is loaded."""
        await super().on_load()
        
        self.router.message.register(self.cmd_warn, Command("warn"))
        self.router.message.register(self.cmd_warnings, Command("warnings"))
        self.router.message.register(self.cmd_resetwarns, Command("resetwarns"))
        
        self.logger.info("Warnings plugin loaded successfully")
    
    def get_commands(self):
        return [
            {"command": "/warn", "description": "Warn a user"},
            {"command": "/warnings", "description": "Show user's warnings"},
            {"command": "/resetwarns", "description": "Clear user's warnings"},
        ]
    
    def _extract_user_id(self, message: Message) -> Optional[int]:
        """Extract user ID from message."""
        if message.reply_to_message:
            return message.reply_to_message.from_user.id
        if message.text:
            parts = message.text.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
        return None
    
    async def cmd_warn(self, message: Message):
        """Warn a user."""
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await message.answer("⚠️ This command can only be used in groups.")
            return
        
        # Check permission
        if not await self.permission_service.can_perform_action(
            self.bot, message.chat.id, message.from_user.id, "warn"
        ):
            await message.answer("⚠️ You don't have permission to warn users.")
            return
        
        target_user_id = self._extract_user_id(message)
        if not target_user_id:
            await message.answer("❌ Reply to a user's message or use `/warn <user_id> [reason]`")
            return
        
        # Extract reason
        parts = message.text.split(maxsplit=2)
        reason = parts[2] if len(parts) > 2 else "No reason provided"
        
        group_id = message.chat.id
        admin_id = message.from_user.id
        
        # Add warning
        await self.permission_service.add_warning(group_id, target_user_id, admin_id, reason)
        
        # Get warning count
        warning_count = await self.permission_service.get_warning_count(group_id, target_user_id)
        
        await message.answer(
            f"⚠️ User `{target_user_id}` warned.\n"
            f"**Reason:** {reason}\n"
            f"**Warnings:** {warning_count}/{self.max_warnings}"
        )
        
        # Auto-kick at max warnings
        if warning_count >= self.max_warnings:
            try:
                await self.bot.ban_chat_member(chat_id=group_id, user_id=target_user_id)
                await self.bot.unban_chat_member(chat_id=group_id, user_id=target_user_id)
                await message.answer(
                    f"🚫 User `{target_user_id}` has been kicked after {self.max_warnings} warnings."
                )
                # Clear warnings after kick
                await self.permission_service.clear_warnings(group_id, target_user_id)
            except TelegramBadRequest as e:
                self.logger.error(f"Failed to kick user {target_user_id}: {e}")
    
    async def cmd_warnings(self, message: Message):
        """Show user's warnings."""
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await message.answer("⚠️ This command can only be used in groups.")
            return
        
        target_user_id = self._extract_user_id(message)
        if not target_user_id:
            await message.answer("❌ Reply to a user's message or use `/warnings <user_id>`")
            return
        
        group_id = message.chat.id
        warnings = await self.permission_service.get_warnings(group_id, target_user_id)
        
        if not warnings:
            await message.answer(f"✅ User `{target_user_id}` has no warnings.")
            return
        
        warnings_text = f"⚠️ **Warnings for user `{target_user_id}`:** ({len(warnings)}/{self.max_warnings})\n\n"
        for i, warning in enumerate(warnings, 1):
            warnings_text += f"{i}. {warning.reason} (by admin `{warning.warned_by}`)\n"
        
        await message.answer(warnings_text)
    
    async def cmd_resetwarns(self, message: Message):
        """Clear user's warnings."""
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await message.answer("⚠️ This command can only be used in groups.")
            return
        
        # Check permission
        if not await self.permission_service.can_perform_action(
            self.bot, message.chat.id, message.from_user.id, "warn"
        ):
            await message.answer("⚠️ You don't have permission to reset warnings.")
            return
        
        target_user_id = self._extract_user_id(message)
        if not target_user_id:
            await message.answer("❌ Reply to a user's message or use `/resetwarns <user_id>`")
            return
        
        group_id = message.chat.id
        await self.permission_service.clear_warnings(group_id, target_user_id)
        await message.answer(f"✅ Warnings cleared for user `{target_user_id}`.")

