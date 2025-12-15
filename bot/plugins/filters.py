"""Message filters plugin for auto-responses."""
import json
import logging
from typing import Optional
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from bot.plugins.base import BasePlugin
from bot.services.group_service import GroupService
from bot.services.permission_service import PermissionService
from database.models import Base
from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime


class MessageFilter(Base):
    """Message filters table."""
    __tablename__ = "filters"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False, index=True)
    keyword = Column(String, nullable=False)
    response = Column(Text, nullable=False)
    buttons = Column(Text, nullable=True)  # JSON
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FiltersPlugin(BasePlugin):
    """Plugin for message filters and auto-responses."""
    
    @property
    def name(self) -> str:
        return "filters"
    
    @property
    def description(self) -> str:
        return "Auto-respond to keywords with custom messages"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        self.group_service = GroupService(db)
        self.permission_service = PermissionService(db)
    
    async def on_load(self):
        """Register all handlers for this plugin."""
        await super().on_load()
        self.router.message.register(self.cmd_filter, Command("filter"))
        self.router.message.register(self.cmd_filters, Command("filters"))
        self.router.message.register(self.cmd_stop, Command("stop"))
        self.router.message.register(self.on_message, F.text)
    
    def get_commands(self) -> list:
        return [
            {"command": "/filter", "description": "Add a filter"},
            {"command": "/filters", "description": "List all filters"},
            {"command": "/stop", "description": "Remove a filter"},
        ]
    
    # Commands
    
    async def cmd_filter(self, message: Message):
        """Add a message filter."""
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
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            await message.answer(
                "❌ **Invalid Usage**\n\n"
                "**Usage:** `/filter <keyword> <response>`\n\n"
                "**Example:**\n"
                "`/filter hello Hello! Welcome to our group!`\n\n"
                "**With buttons:**\n"
                "`/filter rules Check our rules [Rules](https://example.com/rules)`"
            )
            return
        
        keyword = args[1].lower()
        response = args[2]
        
        # Parse buttons
        buttons = self._parse_buttons(response)
        
        # Save to database
        async with get_session() as session:
            # Check if filter already exists
            from sqlalchemy import select
            stmt = select(MessageFilter).where(
                MessageFilter.group_id == message.chat.id,
                MessageFilter.keyword == keyword
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing filter
                existing.response = response
                existing.buttons = json.dumps(buttons) if buttons else None
                existing.created_by = message.from_user.id
                existing.created_at = datetime.utcnow()
            else:
                # Create new filter
                new_filter = MessageFilter(
                    group_id=message.chat.id,
                    keyword=keyword,
                    response=response,
                    buttons=json.dumps(buttons) if buttons else None,
                    created_by=message.from_user.id
                )
                session.add(new_filter)
            
            await session.commit()
        
        await message.answer(
            f"✅ **Filter Added**\n\n"
            f"**Keyword:** `{keyword}`\n"
            f"**Response:** {response}\n\n"
            f"When users say '{keyword}', I'll respond with this message."
        )
    
    async def cmd_filters(self, message: Message):
        """List all filters in the group."""
        # Check if in group
        if message.chat.type not in ["group", "supergroup"]:
            await message.answer("❌ This command can only be used in groups.")
            return
        
        # Get all filters for this group
        async with get_session() as session:
            from sqlalchemy import select
            stmt = select(MessageFilter).where(
                MessageFilter.group_id == message.chat.id
            ).order_by(MessageFilter.keyword)
            result = await session.execute(stmt)
            filters = result.scalars().all()
        
        if not filters:
            await message.answer(
                "📝 **No Filters Set**\n\n"
                "Use `/filter <keyword> <response>` to add a filter."
            )
            return
        
        # Build filter list
        filter_list = []
        for f in filters:
            filter_list.append(f"• `{f.keyword}`")
        
        await message.answer(
            f"📝 **Active Filters ({len(filters)})**\n\n"
            + "\n".join(filter_list) +
            "\n\n**Usage:**\n"
            "`/stop <keyword>` - Remove a filter"
        )
    
    async def cmd_stop(self, message: Message):
        """Remove a filter."""
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
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(
                "❌ **Invalid Usage**\n\n"
                "**Usage:** `/stop <keyword>`\n\n"
                "**Example:**\n"
                "`/stop hello`"
            )
            return
        
        keyword = args[1].lower()
        
        # Delete from database
        async with get_session() as session:
            from sqlalchemy import select, delete
            stmt = delete(MessageFilter).where(
                MessageFilter.group_id == message.chat.id,
                MessageFilter.keyword == keyword
            )
            result = await session.execute(stmt)
            await session.commit()
            
            if result.rowcount == 0:
                await message.answer(f"❌ No filter found for keyword: `{keyword}`")
                return
        
        await message.answer(f"✅ Filter removed: `{keyword}`")
    
    # Event Handlers
    
    async def on_message(self, message: Message):
        """Check if message matches any filters."""
        # Only in groups
        if message.chat.type not in ["group", "supergroup"]:
            return
        
        # Ignore commands
        if message.text and message.text.startswith("/"):
            return
        
        # Check for matching filters
        text = message.text.lower() if message.text else ""
        
        async with get_session() as session:
            from sqlalchemy import select
            stmt = select(MessageFilter).where(
                MessageFilter.group_id == message.chat.id
            )
            result = await session.execute(stmt)
            filters = result.scalars().all()
        
        for f in filters:
            if f.keyword in text:
                # Send response
                buttons = []
                if f.buttons:
                    try:
                        buttons = json.loads(f.buttons)
                    except:
                        pass
                
                keyboard = self._build_keyboard(buttons) if buttons else None
                
                await message.reply(
                    f.response,
                    reply_markup=keyboard
                )
                break  # Only trigger first match
    
    # Helper Methods
    
    def _parse_buttons(self, text: str) -> list:
        """Parse button definitions from text."""
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

