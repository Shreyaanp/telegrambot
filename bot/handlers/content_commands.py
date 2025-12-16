"""Content command handlers - notes, filters, welcome, rules."""
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.container import ServiceContainer
from bot.utils.permissions import require_admin

logger = logging.getLogger(__name__)


def create_content_handlers(container: ServiceContainer) -> Router:
    """
    Create content management command handlers.
    
    Args:
        container: Service container with all dependencies
        
    Returns:
        Router with registered handlers
    """
    router = Router()
    
    # ========== NOTES COMMANDS ==========
    
    @router.message(Command("save"))
    @require_admin
    async def cmd_save(message: Message):
        """
        Save a note.
        
        Usage:
            /save notename Note content here
        """
        parts = message.text.split(maxsplit=2)
        
        if len(parts) < 3:
            await message.reply(
                "❌ **How to use /save:**\n\n"
                "`/save notename Your note content here`\n\n"
                "Example:\n"
                "`/save rules Please be respectful to all members`\n\n"
                "💡 Retrieve with `#notename` or `/get notename`"
            )
            return
        
        note_name = parts[1].lower()
        content = parts[2]
        logger.info(f"[CMD]/save chat={message.chat.id} from={message.from_user.id} note={note_name}")
        
        await container.notes_service.save_note(
            group_id=message.chat.id,
            note_name=note_name,
            content=content,
            admin_id=message.from_user.id
        )
        
        await message.reply(
            f"✅ **Note Saved!**\n\n"
            f"📝 Name: `{note_name}`\n"
            f"📄 Content: _{content[:50]}..._\n\n"
            f"💡 Get it with `#{note_name}` or `/get {note_name}`"
        )
    
    @router.message(Command("get"))
    async def cmd_get(message: Message):
        """Get a note."""
        parts = message.text.split(maxsplit=1)
        
        if len(parts) < 2:
            await message.reply(
                "❌ **How to use /get:**\n\n"
                "`/get notename`\n\n"
                "Or just type `#notename` in chat!"
            )
            return
        
        note_name = parts[1].lower()
        logger.info(f"[CMD]/get chat={message.chat.id} from={message.from_user.id} note={note_name}")
        note = await container.notes_service.get_note(message.chat.id, note_name)
        
        if note:
            await message.reply(note.content)
        else:
            await message.reply(f"❌ Note `{note_name}` not found.\n\n💡 Use `/notes` to see all notes.")
    
    @router.message(Command("notes"))
    async def cmd_notes(message: Message):
        """List all notes."""
        logger.info(f"[CMD]/notes chat={message.chat.id} from={message.from_user.id}")
        notes = await container.notes_service.list_notes(message.chat.id)
        
        if not notes:
            await message.reply(
                "📋 **No notes saved yet**\n\n"
                "💡 Admins can save notes with:\n"
                "`/save notename Your content here`"
            )
            return
        
        text = f"📋 **Saved Notes** ({len(notes)})\n\n"
        buttons = []
        for note in notes[:20]:
            text += f"• `#{note.note_name}`\n"
            buttons.append([InlineKeyboardButton(text=f"❌ Delete {note.note_name}", callback_data=f"note:delete:{note.note_name}")])
        
        if len(notes) > 20:
            text += f"\n_...and {len(notes) - 20} more_"
        
        text += "\n\n💡 Type `#notename` to get a note"
        
        await message.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    @router.message(Command("clear"))
    @require_admin
    async def cmd_clear(message: Message):
        """Delete a note."""
        parts = message.text.split(maxsplit=1)
        
        if len(parts) < 2:
            await message.reply(
                "❌ **How to use /clear:**\n\n"
                "`/clear notename`"
            )
            return
        
        note_name = parts[1].lower()
        logger.info(f"[CMD]/clear chat={message.chat.id} from={message.from_user.id} note={note_name}")
        deleted = await container.notes_service.delete_note(message.chat.id, note_name)
        
        if deleted:
            await message.reply(f"✅ Note `{note_name}` deleted.")
        else:
            await message.reply(f"❌ Note `{note_name}` not found.")
    
    # ========== FILTER COMMANDS ==========
    
    @router.message(Command("filter"))
    @require_admin
    async def cmd_filter(message: Message):
        """Add a message filter."""
        parts = message.text.split(maxsplit=2)
        
        if len(parts) < 3:
            await message.reply(
                "❌ **How to use /filter:**\n\n"
                "`/filter keyword Response text here`\n\n"
                "Example:\n"
                "`/filter hello Hi there! Welcome to the group!`\n\n"
                "💡 When someone says 'hello', bot will respond automatically"
            )
            return
        
        keyword = parts[1].lower()
        response = parts[2]
        logger.info(f"[CMD]/filter chat={message.chat.id} from={message.from_user.id} keyword={keyword}")
        
        await container.filter_service.add_filter(
            group_id=message.chat.id,
            keyword=keyword,
            response=response,
            admin_id=message.from_user.id
        )
        
        await message.reply(
            f"✅ **Filter Added!**\n\n"
            f"🔑 Keyword: `{keyword}`\n"
            f"💬 Response: _{response[:50]}..._\n\n"
            f"💡 Bot will respond when someone says '{keyword}'"
        )
    
    @router.message(Command("filters"))
    async def cmd_filters(message: Message):
        """List all filters."""
        logger.info(f"[CMD]/filters chat={message.chat.id} from={message.from_user.id}")
        filters = await container.filter_service.list_filters(message.chat.id)
        
        if not filters:
            await message.reply(
                "🔍 **No filters set**\n\n"
                "💡 Admins can add filters with:\n"
                "`/filter keyword Response text`"
            )
            return
        
        text = f"🔍 **Active Filters** ({len(filters)})\n\n"
        buttons = []
        for f in filters[:15]:
            text += f"• `{f.keyword}` → {f.response[:30]}...\n"
            buttons.append([InlineKeyboardButton(text=f"❌ Remove {f.keyword}", callback_data=f"filter:remove:{f.keyword}")])
        
        if len(filters) > 15:
            text += f"\n_...and {len(filters) - 15} more_"
        
        await message.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    @router.callback_query(lambda c: c.data and c.data.startswith("note:delete:"))
    @require_admin
    async def note_delete_cb(callback: CallbackQuery):
        """Inline deletion of notes."""
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Invalid note action", show_alert=True)
            return
        _, _, note_name = parts
        deleted = await container.notes_service.delete_note(callback.message.chat.id, note_name)
        if deleted:
            await callback.answer(f"Deleted {note_name}")
            await callback.message.answer(f"✅ Note `{note_name}` deleted.")
        else:
            await callback.answer("Not found", show_alert=True)
    
    @router.message(Command("stop"))
    @require_admin
    async def cmd_stop(message: Message):
        """Remove a filter."""
        parts = message.text.split(maxsplit=1)
        
        if len(parts) < 2:
            await message.reply(
                "❌ **How to use /stop:**\n\n"
                "`/stop keyword`"
            )
            return
        
        keyword = parts[1].lower()
        logger.info(f"[CMD]/stop chat={message.chat.id} from={message.from_user.id} keyword={keyword}")
        removed = await container.filter_service.remove_filter(message.chat.id, keyword)
        
        if removed:
            await message.reply(f"✅ Filter `{keyword}` removed.")
        else:
            await message.reply(f"❌ Filter `{keyword}` not found.")

    @router.callback_query(lambda c: c.data and c.data.startswith("filter:remove:"))
    @require_admin
    async def filter_remove_cb(callback: CallbackQuery):
        """Inline removal of filters."""
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Invalid filter action", show_alert=True)
            return
        _, _, keyword = parts
        removed = await container.filter_service.remove_filter(callback.message.chat.id, keyword)
        if removed:
            await callback.answer(f"Removed {keyword}")
            await callback.message.answer(f"✅ Filter `{keyword}` removed.")
        else:
            await callback.answer("Not found", show_alert=True)
    
    # ========== WELCOME/GOODBYE COMMANDS ==========
    
    @router.message(Command("setwelcome"))
    @require_admin
    async def cmd_setwelcome(message: Message):
        """Set welcome message."""
        parts = message.text.split(maxsplit=1)
        
        if len(parts) < 2:
            await message.reply(
                "❌ **How to use /setwelcome:**\n\n"
                "`/setwelcome Your welcome message here`\n\n"
                "**Variables you can use:**\n"
                "• `{name}` - User's name\n"
                "• `{mention}` - Mention the user\n"
                "• `{group}` - Group name\n"
                "• `{count}` - Member count\n\n"
                "Example:\n"
                "`/setwelcome Welcome {mention} to {group}! We now have {count} members!`"
            )
            return
        
        welcome_text = parts[1]
        
        await container.welcome_service.set_welcome(
            group_id=message.chat.id,
            message=welcome_text,
            enabled=True
        )
        
        await message.reply(
            f"✅ **Welcome Message Set!**\n\n"
            f"📝 Message: _{welcome_text[:100]}..._\n\n"
            f"💡 New members will see this message\n"
            f"🔧 Use `/welcome off` to disable"
        )
    
    @router.message(Command("welcome"))
    async def cmd_welcome(message: Message):
        """Show or toggle welcome message."""
        parts = message.text.split(maxsplit=1)
        
        if len(parts) == 1:
            # Show current welcome
            welcome = await container.welcome_service.get_welcome(message.chat.id)
            
            if welcome:
                enabled, msg = welcome
                status = "✅ Enabled" if enabled else "❌ Disabled"
                await message.reply(
                    f"👋 **Welcome Message**\n\n"
                    f"Status: {status}\n"
                    f"Message: _{msg[:100]}..._\n\n"
                    f"💡 Use `/setwelcome` to change"
                )
            else:
                await message.reply(
                    "ℹ️ No welcome message set\n\n"
                    "💡 Use `/setwelcome Your message` to set one"
                )
            return
    
    @router.message(Command("setgoodbye"))
    @require_admin
    async def cmd_setgoodbye(message: Message):
        """Set goodbye message."""
        parts = message.text.split(maxsplit=1)
        
        if len(parts) < 2:
            await message.reply(
                "❌ **How to use /setgoodbye:**\n\n"
                "`/setgoodbye Your goodbye message here`\n\n"
                "Same variables as welcome: `{name}`, `{mention}`, `{group}`, `{count}`"
            )
            return
        
        goodbye_text = parts[1]
        
        await container.welcome_service.set_goodbye(
            group_id=message.chat.id,
            message=goodbye_text,
            enabled=True
        )
        
        await message.reply(f"✅ **Goodbye Message Set!**\n\n💡 Members leaving will see this message")
    
    # ========== RULES COMMANDS ==========
    
    @router.message(Command("rules"))
    async def cmd_rules(message: Message):
        """Show group rules."""
        from sqlalchemy import select
        from database.db import db
        from database.models import Group
        
        async with db.session() as session:
            result = await session.execute(
                select(Group).where(Group.group_id == message.chat.id)
            )
            group = result.scalar_one_or_none()
            
            if group and group.rules_text:
                await message.reply(
                    f"📜 **Group Rules**\n\n{group.rules_text}\n\n"
                    f"💡 Please follow these rules to keep the group friendly!"
                )
            else:
                await message.reply(
                    "ℹ️ No rules set for this group\n\n"
                    "💡 Admins can set rules with `/setrules`"
                )
    
    @router.message(Command("setrules"))
    @require_admin
    async def cmd_setrules(message: Message):
        """Set group rules."""
        parts = message.text.split(maxsplit=1)
        
        if len(parts) < 2:
            await message.reply(
                "❌ **How to use /setrules:**\n\n"
                "`/setrules Your rules here`\n\n"
                "Example:\n"
                "`/setrules 1. Be respectful\\n2. No spam\\n3. Stay on topic`"
            )
            return
        
        rules_text = parts[1]
        
        from sqlalchemy import select
        from database.db import db
        from database.models import Group
        
        async with db.session() as session:
            result = await session.execute(
                select(Group).where(Group.group_id == message.chat.id)
            )
            group = result.scalar_one_or_none()
            
            if not group:
                group = Group(group_id=message.chat.id, rules_text=rules_text)
                session.add(group)
            else:
                group.rules_text = rules_text
            
            await session.commit()
        
        await message.reply(
            f"✅ **Rules Set!**\n\n"
            f"📜 Rules: _{rules_text[:100]}..._\n\n"
            f"💡 Users can see rules with `/rules`"
        )
    
    return router
