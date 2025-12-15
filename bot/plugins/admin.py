"""Admin commands plugin - group administration tools."""
import logging
from typing import Optional
from aiogram import F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest

from bot.plugins.base import BasePlugin
from bot.services import (
    UserService,
    GroupService,
    SessionService,
    PermissionService
)

logger = logging.getLogger(__name__)

# Import AdminLogsPlugin for logging actions
try:
    from bot.plugins.admin_logs import AdminLogsPlugin
    ADMIN_LOGS_AVAILABLE = True
except ImportError:
    ADMIN_LOGS_AVAILABLE = False


class AdminPlugin(BasePlugin):
    """Plugin for admin commands and group management."""
    
    @property
    def name(self) -> str:
        return "admin"
    
    @property
    def description(self) -> str:
        return "Admin commands for group management"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        
        # Initialize services
        self.user_service = UserService(db)
        self.group_service = GroupService(db)
        self.session_service = SessionService(db)
        self.permission_service = PermissionService(db)
    
    async def on_load(self):
        """Register handlers when plugin is loaded."""
        await super().on_load()
        
        # Register command handlers
        self.router.message.register(self.cmd_vkick, Command("vkick"))
        self.router.message.register(self.cmd_vban, Command("vban"))
        self.router.message.register(self.cmd_settings, Command("settings"))
        self.router.message.register(self.cmd_manual_verify, Command("vverify"))
        
        self.logger.info("Admin plugin loaded successfully")
    
    def get_commands(self):
        return [
            {"command": "/vkick", "description": "Kick a user from the group"},
            {"command": "/vban", "description": "Ban a user from the group"},
            {"command": "/settings", "description": "View/update group settings"},
            {"command": "/vverify", "description": "Manually verify a user"},
        ]
    
    # Helper Methods
    
    async def _check_admin_permission(self, message: Message, action: str) -> bool:
        """Check if user has admin permission for an action."""
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await message.answer("⚠️ This command can only be used in groups.")
            return False
        
        user_id = message.from_user.id
        group_id = message.chat.id
        
        can_perform = await self.permission_service.can_perform_action(
            self.bot, group_id, user_id, action
        )
        
        if not can_perform:
            await message.answer("⚠️ You don't have permission to use this command.")
            return False
        
        return True
    
    def _extract_user_id(self, message: Message) -> Optional[int]:
        """Extract user ID from message (reply or mention)."""
        # Check if replying to a message
        if message.reply_to_message:
            return message.reply_to_message.from_user.id
        
        # Check for @username or user ID in text
        if message.text:
            parts = message.text.split()
            if len(parts) >= 2:
                target = parts[1]
                
                # Try to parse as user ID
                if target.isdigit():
                    return int(target)
                
                # Try to parse as @username
                if target.startswith("@"):
                    # We can't directly resolve username to ID without API call
                    # For now, we'll require reply or numeric ID
                    return None
        
        return None
    
    # Command Handlers
    
    async def cmd_vkick(self, message: Message):
        """
        Kick a user from the group.
        
        Usage:
            /vkick (reply to user's message)
            /vkick <user_id>
        """
        if not await self._check_admin_permission(message, "kick"):
            return
        
        target_user_id = self._extract_user_id(message)
        
        if not target_user_id:
            await message.answer(
                "❌ **Usage:**\n"
                "Reply to a user's message with `/vkick`\n"
                "OR use `/vkick <user_id>`"
            )
            return
        
        group_id = message.chat.id
        
        try:
            # Kick user (ban then unban to allow rejoin)
            await self.bot.ban_chat_member(chat_id=group_id, user_id=target_user_id)
            await self.bot.unban_chat_member(chat_id=group_id, user_id=target_user_id)
            
            # Update database
            await self.group_service.update_member_verification(group_id, target_user_id, False)
            
            # Log action
            if ADMIN_LOGS_AVAILABLE:
                await AdminLogsPlugin.log_action(
                    group_id=group_id,
                    admin_id=message.from_user.id,
                    action="kick",
                    target_user_id=target_user_id
                )
            
            await message.answer(
                f"✅ User `{target_user_id}` has been kicked from the group."
            )
            
            self.logger.info(f"Admin {message.from_user.id} kicked user {target_user_id} from group {group_id}")
            
        except TelegramBadRequest as e:
            await message.answer(f"❌ Failed to kick user: {e}")
            self.logger.error(f"Failed to kick user {target_user_id} from group {group_id}: {e}")
    
    async def cmd_vban(self, message: Message):
        """
        Ban a user from the group.
        
        Usage:
            /vban (reply to user's message) [reason]
            /vban <user_id> [reason]
        """
        if not await self._check_admin_permission(message, "ban"):
            return
        
        target_user_id = self._extract_user_id(message)
        
        if not target_user_id:
            await message.answer(
                "❌ **Usage:**\n"
                "Reply to a user's message with `/vban [reason]`\n"
                "OR use `/vban <user_id> [reason]`"
            )
            return
        
        # Extract reason
        parts = message.text.split(maxsplit=2)
        reason = parts[2] if len(parts) > 2 else "No reason provided"
        
        group_id = message.chat.id
        
        try:
            # Ban user
            await self.bot.ban_chat_member(chat_id=group_id, user_id=target_user_id)
            
            # Log action
            if ADMIN_LOGS_AVAILABLE:
                await AdminLogsPlugin.log_action(
                    group_id=group_id,
                    admin_id=message.from_user.id,
                    action="ban",
                    target_user_id=target_user_id,
                    reason=reason
                )
            
            await message.answer(
                f"🚫 User `{target_user_id}` has been banned from the group.\n"
                f"**Reason:** {reason}"
            )
            
            self.logger.info(f"Admin {message.from_user.id} banned user {target_user_id} from group {group_id}: {reason}")
            
        except TelegramBadRequest as e:
            await message.answer(f"❌ Failed to ban user: {e}")
            self.logger.error(f"Failed to ban user {target_user_id} from group {group_id}: {e}")
    
    async def cmd_settings(self, message: Message):
        """
        View or update group settings.
        
        Usage:
            /settings - View current settings
            /settings timeout <seconds> - Set verification timeout
            /settings autoverify on/off - Toggle auto-verification
            /settings welcome <message> - Set welcome message
        """
        if not await self._check_admin_permission(message, "settings"):
            return
        
        group_id = message.chat.id
        
        # Get or create group
        group = await self.group_service.get_group(group_id)
        if not group:
            group = await self.group_service.create_group(
                group_id=group_id,
                group_name=message.chat.title
            )
        
        # Parse command
        parts = message.text.split(maxsplit=2)
        
        if len(parts) == 1:
            # Show current settings using improved message format
            from bot.utils.messages import settings_display
            
            settings_msg = settings_display(
                group_name=message.chat.title or "this group",
                verification_enabled=group.verification_enabled,
                auto_verify=group.auto_verify_on_join,
                timeout=group.verification_timeout,
                kick_on_timeout=group.kick_on_timeout,
                verification_location=group.verification_location or "group",
                welcome_set=bool(group.welcome_message),
                goodbye_set=bool(getattr(group, 'goodbye_message', None)),
                rules_set=bool(group.rules_text)
            )
            
            await message.answer(settings_msg)
            return
        
        setting = parts[1].lower()
        value = parts[2] if len(parts) > 2 else None
        
        if setting == "timeout":
            if not value or not value.isdigit():
                await message.answer("❌ Please provide a valid timeout in seconds.\nExample: `/settings timeout 120`")
                return
            
            timeout = int(value)
            await self.group_service.set_verification_timeout(group_id, timeout)
            await message.answer(f"✅ Verification timeout set to {timeout}s ({timeout // 60}m)")
            
        elif setting == "autoverify":
            if not value or value.lower() not in ["on", "off"]:
                await message.answer("❌ Please specify `on` or `off`.\nExample: `/settings autoverify on`")
                return
            
            enabled = value.lower() == "on"
            await self.group_service.set_auto_verify(group_id, enabled)
            await message.answer(f"✅ Auto-verification {'enabled' if enabled else 'disabled'}")
            
        elif setting == "location":
            if not value or value.lower() not in ["group", "dm", "both"]:
                await message.answer("❌ Please specify `group`, `dm`, or `both`.\nExample: `/settings location dm`")
                return
            
            location = value.lower()
            await self.group_service.update_group_settings(group_id, verification_location=location)
            
            location_desc = {
                "group": "in the group chat",
                "dm": "in private messages (DM)",
                "both": "in both group and DM"
            }
            await message.answer(f"✅ Verification location set to: **{location.upper()}**\n\nNew members will be verified {location_desc[location]}.")
            
        elif setting == "welcome":
            if not value:
                await message.answer("❌ Please provide a welcome message.\nExample: `/settings welcome Welcome to our group!`")
                return
            
            await self.group_service.set_welcome_message(group_id, value)
            await message.answer(f"✅ Welcome message set to:\n\n{value}")
            
        else:
            await message.answer(
                "❌ Unknown setting. Available settings:\n"
                "- `timeout` - Verification timeout\n"
                "- `autoverify` - Auto-verification on join\n"
                "- `location` - Verification location (group/dm/both)\n"
                "- `welcome` - Welcome message"
            )
    
    async def cmd_manual_verify(self, message: Message):
        """
        Manually verify a user (bypass Mercle verification).
        
        Usage:
            /vverify (reply to user's message)
            /vverify <user_id>
        """
        if not await self._check_admin_permission(message, "verify"):
            return
        
        target_user_id = self._extract_user_id(message)
        
        if not target_user_id:
            await message.answer(
                "❌ **Usage:**\n"
                "Reply to a user's message with `/vverify`\n"
                "OR use `/vverify <user_id>`"
            )
            return
        
        group_id = message.chat.id
        
        # Check if user is already verified globally
        is_verified = await self.user_service.is_verified(target_user_id)
        
        if is_verified:
            await message.answer(f"✅ User `{target_user_id}` is already verified globally.")
            
            # Still update group membership
            await self.group_service.update_member_verification(group_id, target_user_id, True)
            await self.group_service.update_member_mute_status(group_id, target_user_id, False)
            
            # Unmute user
            try:
                await self.bot.restrict_chat_member(
                    chat_id=group_id,
                    user_id=target_user_id,
                    permissions={
                        "can_send_messages": True,
                        "can_send_media_messages": True,
                        "can_send_polls": True,
                        "can_send_other_messages": True,
                        "can_add_web_page_previews": True,
                        "can_invite_users": True,
                    }
                )
            except TelegramBadRequest as e:
                self.logger.error(f"Failed to unmute user {target_user_id}: {e}")
            
            return
        
        # Manually verify user in this group only
        await self.group_service.update_member_verification(group_id, target_user_id, True)
        await self.group_service.update_member_mute_status(group_id, target_user_id, False)
        
        # Unmute user
        try:
            await self.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=target_user_id,
                permissions={
                    "can_send_messages": True,
                    "can_send_media_messages": True,
                    "can_send_polls": True,
                    "can_send_other_messages": True,
                    "can_add_web_page_previews": True,
                    "can_invite_users": True,
                }
            )
            
            await message.answer(
                f"✅ User `{target_user_id}` has been manually verified in this group.\n\n"
                f"⚠️ **Note:** This is a local verification only. User is not globally verified."
            )
            
            self.logger.info(f"Admin {message.from_user.id} manually verified user {target_user_id} in group {group_id}")
            
        except TelegramBadRequest as e:
            await message.answer(f"❌ Failed to unmute user: {e}")
            self.logger.error(f"Failed to unmute user {target_user_id}: {e}")

