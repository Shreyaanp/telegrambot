"""Greetings plugin for welcome and goodbye messages."""
import json
import logging
from typing import Optional
from aiogram import Router, F
from aiogram.types import Message, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from bot.plugins.base import BasePlugin
from bot.services.group_service import GroupService
from bot.services.permission_service import PermissionService


class GreetingsPlugin(BasePlugin):
    """Plugin for handling welcome and goodbye messages with buttons."""
    
    @property
    def name(self) -> str:
        return "greetings"
    
    @property
    def description(self) -> str:
        return "Welcome and goodbye messages with inline buttons"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        self.group_service = GroupService(db)
        self.permission_service = PermissionService(db)
    
    async def on_load(self):
        """Register all handlers for this plugin."""
        await super().on_load()
        self.router.message.register(self.cmd_setwelcome, Command("setwelcome"))
        self.router.message.register(self.cmd_setgoodbye, Command("setgoodbye"))
        self.router.message.register(self.cmd_welcome, Command("welcome"))
        self.router.message.register(self.cmd_goodbye, Command("goodbye"))
        self.router.chat_member.register(self.on_member_left, F.new_chat_member.status == "left")
    
    def get_commands(self) -> list:
        return [
            {"command": "/setwelcome", "description": "Set welcome message with buttons"},
            {"command": "/setgoodbye", "description": "Set goodbye message"},
            {"command": "/welcome", "description": "Test welcome message"},
            {"command": "/goodbye", "description": "Enable/disable goodbye messages"},
        ]
    
    # Commands
    
    async def cmd_setwelcome(self, message: Message):
        """Set welcome message with optional buttons."""
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
        
        # Get message text
        text = message.text.split(maxsplit=1)
        if len(text) < 2:
            await message.answer(
                "❌ **Invalid Usage**\n\n"
                "**Usage:** `/setwelcome <message>`\n\n"
                "**Variables:**\n"
                "• `{name}` - User's first name\n"
                "• `{mention}` - Mention user\n"
                "• `{group}` - Group name\n\n"
                "**Example:**\n"
                "`/setwelcome Welcome {mention} to {group}!`\n\n"
                "**To add buttons:**\n"
                "Use format: `[Button Text](URL)`\n"
                "Example: `[Rules](https://example.com/rules)`"
            )
            return
        
        welcome_text = text[1]
        
        # Parse buttons from message (format: [Text](URL))
        buttons = self._parse_buttons(welcome_text)
        
        # Save to database
        group_id = message.chat.id
        await self.group_service.set_welcome_message(group_id, welcome_text)
        
        if buttons:
            await self.group_service.update_group_settings(
                group_id,
                welcome_message_buttons=json.dumps(buttons)
            )
        
        # Show preview
        preview_text = self._format_welcome_text(
            welcome_text,
            message.from_user.first_name,
            message.from_user.mention_html(),
            message.chat.title
        )
        
        keyboard = self._build_keyboard(buttons) if buttons else None
        
        await message.answer(
            f"✅ **Welcome Message Set!**\n\n"
            f"**Preview:**\n\n{preview_text}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    async def cmd_setgoodbye(self, message: Message):
        """Set goodbye message."""
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
        
        # Get message text
        text = message.text.split(maxsplit=1)
        if len(text) < 2:
            await message.answer(
                "❌ **Invalid Usage**\n\n"
                "**Usage:** `/setgoodbye <message>`\n\n"
                "**Variables:**\n"
                "• `{name}` - User's first name\n"
                "• `{mention}` - Mention user\n"
                "• `{group}` - Group name\n\n"
                "**Example:**\n"
                "`/setgoodbye Goodbye {name}, hope to see you again!`"
            )
            return
        
        goodbye_text = text[1]
        
        # Save to database
        group_id = message.chat.id
        await self.group_service.update_group_settings(
            group_id,
            goodbye_message=goodbye_text,
            goodbye_enabled=True
        )
        
        # Show preview
        preview_text = self._format_welcome_text(
            goodbye_text,
            message.from_user.first_name,
            message.from_user.mention_html(),
            message.chat.title
        )
        
        await message.answer(
            f"✅ **Goodbye Message Set!**\n\n"
            f"**Preview:**\n\n{preview_text}",
            parse_mode="HTML"
        )
    
    async def cmd_welcome(self, message: Message):
        """Test welcome message (admin only)."""
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
        
        # Get group settings
        group = await self.group_service.get_group(message.chat.id)
        if not group or not group.welcome_message:
            await message.answer("❌ No welcome message set. Use `/setwelcome` to set one.")
            return
        
        # Format and send welcome message
        welcome_text = self._format_welcome_text(
            group.welcome_message,
            message.from_user.first_name,
            message.from_user.mention_html(),
            message.chat.title
        )
        
        # Parse buttons
        buttons = []
        if group.welcome_message_buttons:
            try:
                buttons = json.loads(group.welcome_message_buttons)
            except:
                pass
        
        keyboard = self._build_keyboard(buttons) if buttons else None
        
        await message.answer(
            welcome_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    async def cmd_goodbye(self, message: Message):
        """Enable/disable goodbye messages."""
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
        
        # Get argument
        args = message.text.split()
        if len(args) < 2:
            await message.answer(
                "❌ **Invalid Usage**\n\n"
                "**Usage:** `/goodbye <on/off>`\n\n"
                "**Example:**\n"
                "`/goodbye on` - Enable goodbye messages\n"
                "`/goodbye off` - Disable goodbye messages"
            )
            return
        
        action = args[1].lower()
        if action not in ["on", "off"]:
            await message.answer("❌ Please specify `on` or `off`")
            return
        
        enabled = action == "on"
        
        # Update database
        group_id = message.chat.id
        await self.group_service.update_group_settings(
            group_id,
            goodbye_enabled=enabled
        )
        
        await message.answer(
            f"✅ Goodbye messages {'enabled' if enabled else 'disabled'}"
        )
    
    # Event Handlers
    
    async def on_member_left(self, event: ChatMemberUpdated):
        """Handle member leaving the group."""
        try:
            user = event.old_chat_member.user
            chat = event.chat
            
            # Get group settings
            group = await self.group_service.get_group(chat.id)
            if not group or not group.goodbye_enabled or not group.goodbye_message:
                return
            
            # Format goodbye message
            goodbye_text = self._format_welcome_text(
                group.goodbye_message,
                user.first_name,
                user.mention_html(),
                chat.title
            )
            
            # Send goodbye message
            from aiogram import Bot
            bot = Bot.get_current()
            await bot.send_message(
                chat_id=chat.id,
                text=goodbye_text,
                parse_mode="HTML"
            )
        except Exception as e:
            self.logger.error(f"Error sending goodbye message: {e}")
    
    # Helper Methods
    
    def _parse_buttons(self, text: str) -> list:
        """Parse button definitions from text.
        
        Format: [Button Text](URL)
        """
        import re
        
        buttons = []
        pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
        matches = re.findall(pattern, text)
        
        for button_text, url in matches:
            buttons.append({
                "text": button_text,
                "url": url
            })
        
        return buttons
    
    def _build_keyboard(self, buttons: list) -> Optional[InlineKeyboardMarkup]:
        """Build inline keyboard from button definitions."""
        if not buttons:
            return None
        
        keyboard_buttons = []
        for button in buttons:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=button["text"],
                    url=button["url"]
                )
            ])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    def _format_welcome_text(
        self,
        text: str,
        name: str,
        mention: str,
        group_name: str
    ) -> str:
        """Format welcome text with variables."""
        text = text.replace("{name}", name)
        text = text.replace("{mention}", mention)
        text = text.replace("{group}", group_name)
        return text

