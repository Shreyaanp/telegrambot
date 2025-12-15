"""Notes plugin for saving and retrieving group notes."""
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


class Note(Base):
    """Notes table."""
    __tablename__ = "notes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False, index=True)
    note_name = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    media_type = Column(String, nullable=True)  # text, photo, file
    media_file_id = Column(String, nullable=True)
    buttons = Column(Text, nullable=True)  # JSON
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class NotesPlugin(BasePlugin):
    """Plugin for saving and retrieving notes."""
    
    @property
    def name(self) -> str:
        return "notes"
    
    @property
    def description(self) -> str:
        return "Save and retrieve group notes/tags"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        self.group_service = GroupService(db)
        self.permission_service = PermissionService(db)
    
    async def on_load(self):
        """Register all handlers for this plugin."""
        await super().on_load()
        self.router.message.register(self.cmd_save, Command("save"))
        self.router.message.register(self.cmd_get, Command("get"))
        self.router.message.register(self.cmd_notes, Command("notes"))
        self.router.message.register(self.cmd_clear, Command("clear"))
        self.router.message.register(self.on_hashtag, F.text.regexp(r'#\w+'))
    
    def get_commands(self) -> list:
        return [
            {"command": "/save", "description": "Save a note"},
            {"command": "/get", "description": "Get a note"},
            {"command": "/notes", "description": "List all notes"},
            {"command": "/clear", "description": "Delete a note"},
        ]
    
    # Commands
    
    async def cmd_save(self, message: Message):
        """Save a note."""
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
                "**Usage:** `/save <notename> <content>`\n\n"
                "**Example:**\n"
                "`/save rules Please read our rules at example.com`\n\n"
                "**With buttons:**\n"
                "`/save welcome Welcome! [Rules](https://example.com/rules)`\n\n"
                "**Retrieve with:**\n"
                "`/get <notename>` or `#notename`"
            )
            return
        
        note_name = args[1].lower()
        content = args[2]
        
        # Parse buttons
        buttons = self._parse_buttons(content)
        
        # Check for media
        media_type = "text"
        media_file_id = None
        
        if message.reply_to_message:
            if message.reply_to_message.photo:
                media_type = "photo"
                media_file_id = message.reply_to_message.photo[-1].file_id
            elif message.reply_to_message.document:
                media_type = "file"
                media_file_id = message.reply_to_message.document.file_id
        
        # Save to database
        async with get_session() as session:
            from sqlalchemy import select
            stmt = select(Note).where(
                Note.group_id == message.chat.id,
                Note.note_name == note_name
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing note
                existing.content = content
                existing.media_type = media_type
                existing.media_file_id = media_file_id
                existing.buttons = json.dumps(buttons) if buttons else None
                existing.created_by = message.from_user.id
                existing.created_at = datetime.utcnow()
            else:
                # Create new note
                new_note = Note(
                    group_id=message.chat.id,
                    note_name=note_name,
                    content=content,
                    media_type=media_type,
                    media_file_id=media_file_id,
                    buttons=json.dumps(buttons) if buttons else None,
                    created_by=message.from_user.id
                )
                session.add(new_note)
            
            await session.commit()
        
        media_info = f" with {media_type}" if media_type != "text" else ""
        
        await message.answer(
            f"✅ **Note Saved**\n\n"
            f"**Name:** `{note_name}`{media_info}\n\n"
            f"**Retrieve with:**\n"
            f"`/get {note_name}` or `#{note_name}`"
        )
    
    async def cmd_get(self, message: Message):
        """Get a note."""
        # Check if in group
        if message.chat.type not in ["group", "supergroup"]:
            await message.answer("❌ This command can only be used in groups.")
            return
        
        # Parse arguments
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(
                "❌ **Invalid Usage**\n\n"
                "**Usage:** `/get <notename>`\n\n"
                "**Example:**\n"
                "`/get rules`"
            )
            return
        
        note_name = args[1].lower()
        
        # Get from database
        await self._send_note(message.chat.id, note_name, message)
    
    async def cmd_notes(self, message: Message):
        """List all notes."""
        # Check if in group
        if message.chat.type not in ["group", "supergroup"]:
            await message.answer("❌ This command can only be used in groups.")
            return
        
        # Get all notes for this group
        async with get_session() as session:
            from sqlalchemy import select
            stmt = select(Note).where(
                Note.group_id == message.chat.id
            ).order_by(Note.note_name)
            result = await session.execute(stmt)
            notes = result.scalars().all()
        
        if not notes:
            await message.answer(
                "📝 **No Notes Saved**\n\n"
                "Use `/save <notename> <content>` to save a note."
            )
            return
        
        # Build note list
        note_list = []
        for note in notes:
            media_icon = {
                "photo": "📷",
                "file": "📎",
                "text": "📝"
            }.get(note.media_type, "📝")
            note_list.append(f"{media_icon} `#{note.note_name}`")
        
        await message.answer(
            f"📝 **Saved Notes ({len(notes)})**\n\n"
            + "\n".join(note_list) +
            "\n\n**Usage:**\n"
            "`/get <notename>` or `#notename` - Retrieve note\n"
            "`/clear <notename>` - Delete note"
        )
    
    async def cmd_clear(self, message: Message):
        """Delete a note."""
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
                "**Usage:** `/clear <notename>`\n\n"
                "**Example:**\n"
                "`/clear rules`"
            )
            return
        
        note_name = args[1].lower()
        
        # Delete from database
        async with get_session() as session:
            from sqlalchemy import delete
            stmt = delete(Note).where(
                Note.group_id == message.chat.id,
                Note.note_name == note_name
            )
            result = await session.execute(stmt)
            await session.commit()
            
            if result.rowcount == 0:
                await message.answer(f"❌ No note found: `{note_name}`")
                return
        
        await message.answer(f"✅ Note deleted: `{note_name}`")
    
    # Event Handlers
    
    async def on_hashtag(self, message: Message):
        """Handle hashtag mentions of notes."""
        # Only in groups
        if message.chat.type not in ["group", "supergroup"]:
            return
        
        # Extract hashtags
        import re
        hashtags = re.findall(r'#(\w+)', message.text)
        
        if not hashtags:
            return
        
        # Try to find and send the first matching note
        for tag in hashtags:
            await self._send_note(message.chat.id, tag.lower(), message)
            break  # Only send first match
    
    # Helper Methods
    
    async def _send_note(self, group_id: int, note_name: str, message: Message):
        """Send a note to the chat."""
        # Get from database
        async with get_session() as session:
            from sqlalchemy import select
            stmt = select(Note).where(
                Note.group_id == group_id,
                Note.note_name == note_name
            )
            result = await session.execute(stmt)
            note = result.scalar_one_or_none()
        
        if not note:
            await message.answer(f"❌ Note not found: `{note_name}`")
            return
        
        # Parse buttons
        buttons = []
        if note.buttons:
            try:
                buttons = json.loads(note.buttons)
            except:
                pass
        
        keyboard = self._build_keyboard(buttons) if buttons else None
        
        # Send based on media type
        if note.media_type == "photo" and note.media_file_id:
            await message.answer_photo(
                photo=note.media_file_id,
                caption=note.content,
                reply_markup=keyboard
            )
        elif note.media_type == "file" and note.media_file_id:
            await message.answer_document(
                document=note.media_file_id,
                caption=note.content,
                reply_markup=keyboard
            )
        else:
            await message.answer(
                note.content,
                reply_markup=keyboard
            )
    
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

