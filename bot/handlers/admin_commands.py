"""Admin command handlers - kick, ban, warn, whitelist, settings."""
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.container import ServiceContainer
from bot.utils.permissions import (
    require_restrict_permission,
    require_admin,
    extract_user_and_reason,
    get_user_mention,
    format_time_delta,
    is_user_admin,
    is_bot_admin,
    can_restrict_members,
    has_role_permission
)
from aiogram import Bot
from bot.utils.permissions import can_pin_messages
from database.models import Permission

logger = logging.getLogger(__name__)


def create_admin_handlers(container: ServiceContainer) -> Router:
    """
    Create admin command handlers.
    
    Args:
        container: Service container with all dependencies
        
    Returns:
        Router with registered handlers
    """
    router = Router()
    
    # ========== MODERATION COMMANDS ==========
    
    @router.message(Command("kick", "vkick"))
    @require_restrict_permission
    async def cmd_kick(message: Message):
        """
        Kick a user from the group.
        
        Usage:
            /kick (reply to user) [reason]
            /kick @username [reason]
            /kick user_id [reason]
        """
        user_id, reason = await extract_user_and_reason(message)
        logger.info(f"[CMD]/kick chat={message.chat.id} from={message.from_user.id} target={user_id} reason={reason}")
        
        if not user_id:
            await message.reply(
                "❌ I couldn't find that user.\n\n"
                "Reply to the user's message with:\n"
                "`/kick [reason]`\n\n"
                "Or use their numeric ID:\n"
                "`/kick <user_id> [reason]`\n\n"
                "Tip: `/actions` on a reply shows buttons to avoid username issues."
            )
            return
        
        # Kick the user
        success = await container.admin_service.kick_user(
            bot=message.bot,
            group_id=message.chat.id,
            user_id=user_id,
            admin_id=message.from_user.id,
            reason=reason
        )
        await container.metrics_service.incr_admin_action("kick", message.chat.id)
        
        if success:
            user_mention = await get_user_mention(message, user_id)
            reason_text = f"\n**Reason:** {reason}" if reason else ""
            await message.reply(
                f"✅ **User Kicked**\n\n"
                f"👤 User: {user_mention}\n"
                f"👮 Admin: {message.from_user.mention_html()}"
                f"{reason_text}"
            )
        else:
            await message.reply("❌ Failed to kick user. Make sure I have admin rights.")

    @router.message(Command("actions"))
    @require_restrict_permission
    async def cmd_actions(message: Message):
        """
        Show inline admin actions for the replied user.
        
        Usage: reply to a user's message with /actions
        """
        if not message.reply_to_message:
            await message.reply("Reply to a user's message with /actions to manage them.")
            return
        
        target_id = message.reply_to_message.from_user.id
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🚫 Kick", callback_data=f"act:kick:{target_id}:0"),
                    InlineKeyboardButton(text="⛔ Ban", callback_data=f"act:ban:{target_id}:0"),
                ],
                [
                    InlineKeyboardButton(text="🔇 Mute 10m", callback_data=f"act:mute:{target_id}:600"),
                    InlineKeyboardButton(text="🔇 Mute 1h", callback_data=f"act:mute:{target_id}:3600"),
                    InlineKeyboardButton(text="🔇 Mute 24h", callback_data=f"act:mute:{target_id}:86400"),
                ],
                [
                    InlineKeyboardButton(text="🛑 Temp-ban 1h", callback_data=f"act:tempban:{target_id}:3600"),
                    InlineKeyboardButton(text="🛑 Temp-ban 24h", callback_data=f"act:tempban:{target_id}:86400"),
                ],
                [
                    InlineKeyboardButton(text="🧹 Purge 10", callback_data=f"act:purge:{target_id}:10"),
                    InlineKeyboardButton(text="🧹 Purge 25", callback_data=f"act:purge:{target_id}:25"),
                ],
                [
                    InlineKeyboardButton(text="🔊 Unmute", callback_data=f"act:unmute:{target_id}:0"),
                    InlineKeyboardButton(text="⚠️ Warn", callback_data=f"act:warn:{target_id}:0"),
                ],
            ]
        )
        await message.reply("Choose an action:", reply_markup=keyboard)
    
    @router.message(Command("ban", "vban"))
    @require_restrict_permission
    async def cmd_ban(message: Message):
        """
        Ban a user from the group.
        
        Usage:
            /ban (reply to user) [reason]
            /ban @username [reason]
        """
        user_id, reason = await extract_user_and_reason(message)
        logger.info(f"[CMD]/ban chat={message.chat.id} from={message.from_user.id} target={user_id} reason={reason}")
        
        if not user_id:
            await message.reply(
                "❌ I couldn't find that user.\n\n"
                "Reply to the user's message with:\n"
                "`/ban [reason]`\n\n"
                "Or use their numeric ID:\n"
                "`/ban <user_id> [reason]`\n\n"
                "Tip: `/actions` on a reply shows buttons to avoid username issues."
            )
            return
        
        # Ban the user
        success = await container.admin_service.ban_user(
            bot=message.bot,
            group_id=message.chat.id,
            user_id=user_id,
            admin_id=message.from_user.id,
            reason=reason
        )
        await container.metrics_service.incr_admin_action("ban", message.chat.id)
        
        if success:
            user_mention = await get_user_mention(message, user_id)
            reason_text = f"\n**Reason:** {reason}" if reason else ""
            await message.reply(
                f"🚫 **User Banned**\n\n"
                f"👤 User: {user_mention}\n"
                f"👮 Admin: {message.from_user.mention_html()}"
                f"{reason_text}\n\n"
                f"💡 Use `/unban` to lift the ban"
            )
        else:
            await message.reply("❌ Failed to ban user. Make sure I have admin rights.")
    
    @router.message(Command("unban", "vunban"))
    @require_restrict_permission
    async def cmd_unban(message: Message):
        """Unban a user from the group."""
        user_id, _ = await extract_user_and_reason(message)
        logger.info(f"[CMD]/unban chat={message.chat.id} from={message.from_user.id} target={user_id}")
        
        if not user_id:
            await message.reply(
                "❌ I couldn't find that user.\n\n"
                "Reply to a message with `/unban` or use their numeric ID:\n"
                "`/unban <user_id>`\n\n"
                "Tip: `/actions` on a reply shows buttons to avoid username issues."
            )
            return
        
        success = await container.admin_service.unban_user(
            bot=message.bot,
            group_id=message.chat.id,
            user_id=user_id,
            admin_id=message.from_user.id
        )
        await container.metrics_service.incr_admin_action("unban", message.chat.id)
        
        if success:
            await message.reply(f"✅ User {user_id} has been unbanned.")
        else:
            await message.reply("❌ Failed to unban user.")
    
    @router.message(Command("mute"))
    @require_restrict_permission
    async def cmd_mute(message: Message):
        """Mute a user in the group."""
        user_id, reason = await extract_user_and_reason(message)
        logger.info(f"[CMD]/mute chat={message.chat.id} from={message.from_user.id} target={user_id} reason={reason}")
        
        if not user_id:
            await message.reply(
                "❌ I couldn't find that user.\n\n"
                "Reply to the user's message with `/mute [reason]` or use their numeric ID:\n"
                "`/mute <user_id> [reason]`\n\n"
                "Tip: `/actions` on a reply shows buttons to avoid username issues."
            )
            return
        
        success = await container.admin_service.mute_user(
            bot=message.bot,
            group_id=message.chat.id,
            user_id=user_id,
            admin_id=message.from_user.id,
            reason=reason
        )
        await container.metrics_service.incr_admin_action("mute", message.chat.id)
        
        if success:
            user_mention = await get_user_mention(message, user_id)
            reason_text = f"\n**Reason:** {reason}" if reason else ""
            await message.reply(
                f"🔇 **User Muted**\n\n"
                f"👤 User: {user_mention}\n"
                f"👮 Admin: {message.from_user.mention_html()}"
                f"{reason_text}\n\n"
                f"💡 Use `/unmute` to restore their voice"
            )
        else:
            await message.reply("❌ Failed to mute user.")
    
    @router.message(Command("unmute"))
    @require_restrict_permission
    async def cmd_unmute(message: Message):
        """Unmute a user in the group."""
        user_id, _ = await extract_user_and_reason(message)
        logger.info(f"[CMD]/unmute chat={message.chat.id} from={message.from_user.id} target={user_id}")
        
        if not user_id:
            await message.reply(
                "❌ I couldn't find that user.\n\n"
                "Reply to a message with `/unmute` or use their numeric ID:\n"
                "`/unmute <user_id>`\n\n"
                "Tip: `/actions` on a reply shows buttons to avoid username issues."
            )
            return
        
        success = await container.admin_service.unmute_user(
            bot=message.bot,
            group_id=message.chat.id,
            user_id=user_id,
            admin_id=message.from_user.id
        )
        await container.metrics_service.incr_admin_action("unmute", message.chat.id)
        
        if success:
            user_mention = await get_user_mention(message, user_id)
            await message.reply(f"🔊 **User Unmuted**\n\n👤 {user_mention} can now speak again!")
        else:
            await message.reply("❌ Failed to unmute user.")

    @router.message(Command("purge"))
    @require_restrict_permission
    async def cmd_purge(message: Message):
        """
        Purge messages from a replied message up to the command message.
        Usage: reply to a message with /purge
        """
        if not message.reply_to_message:
            await message.reply("Reply to a message with /purge to delete from that message up to here.")
            return
        start_id = message.reply_to_message.message_id
        end_id = message.message_id
        deleted = 0
        for mid in range(start_id, end_id + 1):
            try:
                await message.bot.delete_message(message.chat.id, mid)
                deleted += 1
            except Exception as e:
                logger.debug(f"Purge delete failed for {mid}: {e}")
        await message.answer(f"🧹 Purged {deleted} messages.")
    
    # ========== WARNING SYSTEM ==========
    
    @router.message(Command("warn"))
    @require_admin
    async def cmd_warn(message: Message):
        """Warn a user."""
        user_id, reason = await extract_user_and_reason(message)
        logger.info(f"[CMD]/warn chat={message.chat.id} from={message.from_user.id} target={user_id} reason={reason}")
        
        if not user_id:
            await message.reply(
                "❌ I couldn't find that user.\n\n"
                "Reply to the user's message with `/warn [reason]` or use their numeric ID:\n"
                "`/warn <user_id> [reason]`\n\n"
                "Tip: `/actions` on a reply shows buttons to avoid username issues."
            )
            return
        
        warn_count, warn_limit = await container.admin_service.warn_user(
            group_id=message.chat.id,
            user_id=user_id,
            admin_id=message.from_user.id,
            reason=reason
        )
        await container.metrics_service.incr_admin_action("warn", message.chat.id)
        
        user_mention = await get_user_mention(message, user_id)
        reason_text = f"\n**Reason:** {reason}" if reason else ""
        
        if warn_count >= warn_limit:
            # Auto-kick on limit reached
            await container.admin_service.kick_user(
                bot=message.bot,
                group_id=message.chat.id,
                user_id=user_id,
                admin_id=message.from_user.id,
                reason=f"Reached warning limit ({warn_limit} warnings)"
            )
            await message.reply(
                f"⚠️ **Warning Limit Reached!**\n\n"
                f"👤 User: {user_mention}\n"
                f"📊 Warnings: {warn_count}/{warn_limit}"
                f"{reason_text}\n\n"
                f"🚫 User has been **kicked** from the group."
            )
        else:
            await message.reply(
                f"⚠️ **User Warned**\n\n"
                f"👤 User: {user_mention}\n"
                f"👮 Admin: {message.from_user.mention_html()}\n"
                f"📊 Warnings: {warn_count}/{warn_limit}"
                f"{reason_text}\n\n"
                f"💡 Use `/warns` to check warnings"
            )
    
    @router.message(Command("warns", "warnings"))
    async def cmd_warns(message: Message):
        """Check user's warnings."""
        user_id, _ = await extract_user_and_reason(message)
        logger.info(f"[CMD]/warns chat={message.chat.id} from={message.from_user.id} target={user_id}")
        
        if not user_id:
            # Check own warnings
            user_id = message.from_user.id
        
        warnings = await container.admin_service.get_warnings(
            group_id=message.chat.id,
            user_id=user_id
        )
        
        if not warnings:
            await message.reply(f"✅ User has no warnings.")
            return
        
        user_mention = await get_user_mention(message, user_id)
        warns_text = f"⚠️ **Warnings for {user_mention}**\n\n"
        warns_text += f"**Total:** {len(warnings)} warnings\n\n"
        
        for i, warn in enumerate(warnings[:5], 1):  # Show last 5
            reason = warn.reason or "No reason provided"
            date = warn.warned_at.strftime("%Y-%m-%d %H:%M")
            warns_text += f"{i}. {reason}\n   _{date}_\n\n"
        
        if len(warnings) > 5:
            warns_text += f"_...and {len(warnings) - 5} more_\n\n"
        
        warns_text += "💡 Use `/resetwarns` to clear warnings (admin only)"
        
        await message.reply(warns_text)
    
    @router.message(Command("resetwarns"))
    @require_admin
    async def cmd_resetwarns(message: Message):
        """Reset user's warnings."""
        user_id, _ = await extract_user_and_reason(message)
        logger.info(f"[CMD]/resetwarns chat={message.chat.id} from={message.from_user.id} target={user_id}")
        
        if not user_id:
            await message.reply(
                "❌ I couldn't find that user.\n\n"
                "Reply to the user's message with `/resetwarns` or use their numeric ID:\n"
                "`/resetwarns <user_id>`\n\n"
                "Tip: `/actions` on a reply shows buttons to avoid username issues."
            )
            return
        
        count = await container.admin_service.reset_warnings(
            group_id=message.chat.id,
            user_id=user_id,
            admin_id=message.from_user.id
        )
        await container.metrics_service.incr_admin_action("resetwarns", message.chat.id)
        
        user_mention = await get_user_mention(message, user_id)
        await message.reply(
            f"✅ **Warnings Reset**\n\n"
            f"👤 User: {user_mention}\n"
            f"🗑️ Removed: {count} warning{'s' if count != 1 else ''}\n\n"
            f"Fresh start! 🎉"
        )
    
    # ========== WHITELIST COMMANDS ==========
    
    @router.message(Command("whitelist"))
    @require_admin
    async def cmd_whitelist(message: Message):
        """Add user to whitelist or show whitelist."""
        parts = message.text.split(maxsplit=2)
        logger.info(f"[CMD]/whitelist chat={message.chat.id} from={message.from_user.id} action={parts[1] if len(parts)>1 else 'show'}")
        
        if len(parts) == 1:
            # Show whitelist
            whitelist = await container.whitelist_service.get_whitelist(message.chat.id)
            
            if not whitelist:
                await message.reply("📋 **Whitelist is empty**\n\nUse `/whitelist add @user` to add users.")
                return
            
            text = f"📋 **Whitelisted Users** ({len(whitelist)})\n\n"
            buttons = []
            for entry in whitelist[:10]:
                reason = f" - {entry.reason}" if entry.reason else ""
                text += f"• User {entry.telegram_id}{reason}\n"
                buttons.append([InlineKeyboardButton(text=f"❌ Remove {entry.telegram_id}", callback_data=f"wl:remove:{entry.telegram_id}")])
            
            if len(whitelist) > 10:
                text += f"\n_...and {len(whitelist) - 10} more_"
            
            await message.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
            return
        
        action = parts[1].lower() if len(parts) > 1 else ""
        
        if action == "add":
            user_id, reason = await extract_user_and_reason(message)
            
            if not user_id:
                await message.reply(
                    "❌ **How to use /whitelist add:**\n\n"
                    "Reply to a user's message:\n"
                    "`/whitelist add [reason]`"
                )
                return
            
            added = await container.whitelist_service.add_to_whitelist(
                group_id=message.chat.id,
                user_id=user_id,
                admin_id=message.from_user.id,
                reason=reason
            )
            await container.metrics_service.incr_admin_action("whitelist_add", message.chat.id)
            
            if added:
                user_mention = await get_user_mention(message, user_id)
                await message.reply(
                    f"✅ **Added to Whitelist**\n\n"
                    f"👤 {user_mention} can now bypass verification!"
                )
            else:
                await message.reply("ℹ️ User is already whitelisted.")
        
        elif action == "remove":
            user_id, _ = await extract_user_and_reason(message)
            
            if not user_id:
                await message.reply(
                    "❌ **How to use /whitelist remove:**\n\n"
                    "Reply to a user's message:\n"
                    "`/whitelist remove`"
                )
                return
            
            removed = await container.whitelist_service.remove_from_whitelist(
                group_id=message.chat.id,
                user_id=user_id
            )
            await container.metrics_service.incr_admin_action("whitelist_remove", message.chat.id)
            
            if removed:
                await message.reply("✅ User removed from whitelist.")
            else:
                await message.reply("ℹ️ User was not whitelisted.")
        
        else:
            await message.reply(
                "❌ **Whitelist Commands:**\n\n"
                "`/whitelist` - Show whitelist\n"
                "`/whitelist add @user [reason]` - Add to whitelist\n"
                "`/whitelist remove @user` - Remove from whitelist"
            )
    
    @router.callback_query(lambda c: c.data and c.data.startswith("wl:remove:"))
    @require_admin
    async def wl_remove_cb(callback: CallbackQuery):
        """Inline whitelist removal."""
        try:
            _, _, user_str = callback.data.split(":")
            target_id = int(user_str)
        except Exception:
            await callback.answer("Invalid whitelist action", show_alert=True)
            return
        removed = await container.whitelist_service.remove_from_whitelist(callback.message.chat.id, target_id)
        if removed:
            await callback.answer("Removed")
            await callback.message.answer(f"✅ Removed `{target_id}` from whitelist.")
        else:
            await callback.answer("Not whitelisted", show_alert=True)
    
    @router.message(Command("checkperms"))
    @require_admin
    async def cmd_checkperms(message: Message):
        """Check bot and your permissions in this group."""
        await send_perm_check(message.bot, message.chat.id, message.from_user.id, reply_to=message)
    
    # ========== SETTINGS ==========
    
    @router.message(Command("settings"))
    @require_admin
    async def cmd_settings(message: Message):
        """
        View or update group settings.
        
        Examples:
            /settings
            /settings timeout 240
            /settings action kick
            /settings antiflood 15
            /settings welcome off
            /settings verify off
        """
        parts = message.text.split()
        
        # Show settings
        if len(parts) == 1:
            group = await container.group_service.get_or_create_group(message.chat.id)
            action = "kick" if group.kick_unverified else "mute"
            text = (
                "⚙️ **Group Settings**\n\n"
                f"• Verification: {'✅ On' if group.verification_enabled else '❌ Off'}\n"
                f"• Timeout: {group.verification_timeout}s\n"
                f"• Action on timeout: {action}\n"
                f"• Welcome message: {'✅ On' if group.welcome_enabled else '❌ Off'}\n"
                f"• Antiflood: {'✅ On' if group.antiflood_enabled else '❌ Off'} "
                f"(limit {group.antiflood_limit}/min)\n\n"
                "Update examples:\n"
                "`/settings timeout 240`\n"
                "`/settings action kick`\n"
                "`/settings antiflood 15`\n"
                "`/settings welcome off`\n"
                "`/settings verify off`"
            )
            await message.reply(text)
            return
        
        if len(parts) < 3:
            await message.reply("Usage: `/settings <option> <value>`\nTry `/settings` to view options.")
            return
        
        option = parts[1].lower()
        value = parts[2].lower()
        
        if option == "timeout":
            try:
                seconds = int(value)
                updated = await container.group_service.update_setting(
                    message.chat.id,
                    verification_timeout=seconds
                )
                await message.reply(f"✅ Timeout set to {updated.verification_timeout}s")
            except ValueError:
                await message.reply("Timeout must be a number (seconds).")
        elif option == "action":
            if value not in ("kick", "mute"):
                await message.reply("Action must be `kick` or `mute`.")
                return
            updated = await container.group_service.update_setting(
                message.chat.id,
                action_on_timeout=value
            )
            await message.reply(f"✅ Action on timeout set to `{value}`")
        elif option == "antiflood":
            try:
                limit = int(value)
                updated = await container.group_service.update_setting(
                    message.chat.id,
                    antiflood_limit=limit,
                    antiflood_enabled=True
                )
                await message.reply(f"✅ Antiflood limit set to {updated.antiflood_limit} msgs/min")
            except ValueError:
                await message.reply("Antiflood limit must be a number.")
        elif option == "welcome":
            if value not in ("on", "off"):
                await message.reply("Welcome value must be `on` or `off`.")
                return
            updated = await container.group_service.update_setting(
                message.chat.id,
                welcome_enabled=(value == "on")
            )
            await message.reply(f"✅ Welcome message turned {'on' if updated.welcome_enabled else 'off'}")
        elif option in ("verify", "verification"):
            if value not in ("on", "off"):
                await message.reply("Verification value must be `on` or `off`.")
                return
            updated = await container.group_service.update_setting(
                message.chat.id,
                verification_enabled=(value == "on")
            )
            await message.reply(f"✅ Verification requirement turned {'on' if updated.verification_enabled else 'off'}")
        else:
            await message.reply("Unknown option. Valid options: timeout, action, antiflood, welcome, verify.")

    # ========== PIN/UNPIN ==========
    
    @router.message(Command("pin"))
    @require_admin
    async def cmd_pin(message: Message):
        """Pin a message (reply required)."""
        if not message.reply_to_message:
            await message.reply("Reply to a message with /pin to pin it.")
            return
        if not await can_pin_messages(message.bot, message.chat.id, message.from_user.id):
            await message.reply("❌ You need pin permissions to use this.")
            return
        if not await can_pin_messages(message.bot, message.chat.id, message.bot.id):
            await message.reply("❌ Bot needs pin permissions to do this.")
            return
        try:
            await message.bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
            await message.reply("✅ Message pinned.")
        except Exception as e:
            logger.error(f"Failed to pin message: {e}")
            await message.reply("❌ Failed to pin message.")
    
    @router.message(Command("unpin"))
    @require_admin
    async def cmd_unpin(message: Message):
        """Unpin last message or replied message."""
        if not await can_pin_messages(message.bot, message.chat.id, message.from_user.id):
            await message.reply("❌ You need pin permissions to use this.")
            return
        if not await can_pin_messages(message.bot, message.chat.id, message.bot.id):
            await message.reply("❌ Bot needs pin permissions to do this.")
            return
        try:
            if message.reply_to_message:
                await message.bot.unpin_chat_message(message.chat.id, message.reply_to_message.message_id)
            else:
                await message.bot.unpin_chat_message(message.chat.id)
            await message.reply("✅ Unpinned.")
        except Exception as e:
            logger.error(f"Failed to unpin message: {e}")
            await message.reply("❌ Failed to unpin.")

    # ========== LOCKS ==========
    
    @router.message(Command("lock"))
    @require_admin
    async def cmd_lock(message: Message):
        """
        Lock content types.
        Usage: /lock links|media|all
        """
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("Usage: `/lock links` or `/lock media` or `/lock all`")
            return
        arg = parts[1].lower()
        lock_links = lock_media = None
        if arg == "links":
            lock_links = True
        elif arg == "media":
            lock_media = True
        elif arg == "all":
            lock_links = True
            lock_media = True
        else:
            await message.reply("Unknown lock target. Use links, media, or all.")
            return
        await container.lock_service.set_lock(message.chat.id, lock_links=lock_links, lock_media=lock_media)
        await message.reply("✅ Locks updated.")
    
    @router.message(Command("unlock"))
    @require_admin
    async def cmd_unlock(message: Message):
        """
        Unlock content types.
        Usage: /unlock links|media|all
        """
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("Usage: `/unlock links` or `/unlock media` or `/unlock all`")
            return
        arg = parts[1].lower()
        lock_links = lock_media = None
        if arg == "links":
            lock_links = False
        elif arg == "media":
            lock_media = False
        elif arg == "all":
            lock_links = False
            lock_media = False
        else:
            await message.reply("Unknown unlock target. Use links, media, or all.")
            return
        await container.lock_service.set_lock(message.chat.id, lock_links=lock_links, lock_media=lock_media)
        await message.reply("✅ Locks updated.")
    
    # ========== ROLES ==========
    
    @router.message(Command("roles"))
    @require_admin
    async def cmd_roles(message: Message):
        """
        Manage custom roles.
        Usage:
            /roles            -> list
            /roles add @user role   (role: moderator|helper)
            /roles remove @user
        """
        parts = message.text.split()
        if len(parts) == 1:
            roles = await container.roles_service.list_roles(message.chat.id)
            if not roles:
                await message.reply("ℹ️ No roles assigned in this group.")
                return
            text = "🧑‍💼 **Roles**\n\n"
            for r in roles[:15]:
                text += f"- `{r.telegram_id}` as *{r.role}*\n"
            if len(roles) > 15:
                text += f"...and {len(roles)-15} more."
            await message.reply(text, parse_mode="Markdown")
            return
        
        action = parts[1].lower()
        if action == "add" and len(parts) >= 4:
            user_id, _ = await extract_user_and_reason(message)
            role = parts[3].lower() if len(parts) >= 4 else "moderator"
            if role not in ["moderator", "helper"]:
                await message.reply("Role must be `moderator` or `helper`.")
                return
            if not user_id:
                await message.reply("Reply to the user or provide their ID for /roles add.")
                return
            perm = await container.roles_service.add_role(
                group_id=message.chat.id,
                user_id=user_id,
                role=role,
                granted_by=message.from_user.id
            )
            await message.reply(f"✅ Assigned role *{perm.role}* to `{user_id}`.", parse_mode="Markdown")
        elif action == "remove":
            user_id, _ = await extract_user_and_reason(message)
            if not user_id:
                await message.reply("Reply to the user or provide their ID for /roles remove.")
                return
            removed = await container.roles_service.remove_role(message.chat.id, user_id)
            if removed:
                await message.reply(f"✅ Removed role for `{user_id}`.", parse_mode="Markdown")
            else:
                await message.reply("ℹ️ No role found for that user.")
        else:
            await message.reply("Usage: `/roles`, `/roles add @user role`, `/roles remove @user`")
    
    return router
    
    @router.callback_query(lambda c: c.data and c.data.startswith("checkperms:"))
    async def checkperms_cb(callback: CallbackQuery):
        """Callback to check permissions from setup card."""
        from bot.handlers.admin_commands import send_perm_check  # avoid circular at import time
        parts = callback.data.split(":")
        if len(parts) != 2:
            await callback.answer("Invalid", show_alert=True)
            return
        try:
            group_id = int(parts[1])
        except ValueError:
            await callback.answer("Invalid group", show_alert=True)
            return
        await send_perm_check(callback.bot, group_id, callback.from_user.id, reply_to=callback.message)


async def send_perm_check(bot: Bot, chat_id: int, admin_id: int, reply_to: Message):
    """Send permission check summary."""
    bot_info = await bot.get_me()
    bot_member = await bot.get_chat_member(chat_id, bot_info.id)
    admin_member = await bot.get_chat_member(chat_id, admin_id)
    
    def fmt(member):
        perms = []
        if getattr(member, "can_restrict_members", False):
            perms.append("restrict")
        if getattr(member, "can_delete_messages", False):
            perms.append("delete")
        if getattr(member, "can_pin_messages", False):
            perms.append("pin")
        if getattr(member, "can_promote_members", False):
            perms.append("promote")
        return member.status, perms
    
    bot_status, bot_perms = fmt(bot_member)
    admin_status, admin_perms = fmt(admin_member)
    
    text = (
        "🔎 **Permissions Check**\n\n"
        f"Bot `{bot_info.username}`: {bot_status}\n"
        f"- Perms: {', '.join(bot_perms) if bot_perms else 'none'}\n\n"
        f"You: {admin_status}\n"
        f"- Perms: {', '.join(admin_perms) if admin_perms else 'none'}\n\n"
        "Required: bot needs Restrict Members and Delete Messages."
    )
    await reply_to.reply(text, parse_mode="Markdown")

# ========== CALLBACK HANDLERS ==========

    @router.callback_query(lambda c: c.data and c.data.startswith("act:"))
    async def admin_action_callback(callback: CallbackQuery):
        """
        Handle inline admin actions invoked from /actions.
        Format: act:<action>:<target_id>:<duration_seconds>
        """
        data = callback.data.split(":")
        if len(data) != 4:
            await callback.answer("Invalid action", show_alert=True)
            return
        
        _, action, target_str, duration_str = data
        chat_id = callback.message.chat.id
        admin_id = callback.from_user.id
        
        # Permission checks
        if not await is_user_admin(callback.bot, chat_id, admin_id):
            await callback.answer("You must be an admin to do that.", show_alert=True)
            return
        if not await is_bot_admin(callback.bot, chat_id):
            await callback.answer("Bot must be admin with restrict rights.", show_alert=True)
            return
        if not await can_restrict_members(callback.bot, chat_id, admin_id):
            await callback.answer("You need 'Restrict Members' permission.", show_alert=True)
            return
        
        try:
            target_id = int(target_str)
            duration = int(duration_str)
        except ValueError:
            await callback.answer("Invalid target.", show_alert=True)
            return
        
        user_mention = f"user {target_id}"
        success = False
        
        if action == "kick":
            success = await container.admin_service.kick_user(
                bot=callback.bot,
                group_id=chat_id,
                user_id=target_id,
                admin_id=admin_id,
                reason="(via /actions)"
            )
        elif action == "ban":
            success = await container.admin_service.ban_user(
                bot=callback.bot,
                group_id=chat_id,
                user_id=target_id,
                admin_id=admin_id,
                reason="(via /actions)"
            )
        elif action == "tempban":
            from datetime import datetime, timedelta
            until = datetime.utcnow() + timedelta(seconds=duration or 3600)
            success = await container.admin_service.ban_user(
                bot=callback.bot,
                group_id=chat_id,
                user_id=target_id,
                admin_id=admin_id,
                reason="(via /actions tempban)",
                until_date=until
            )
        elif action == "mute":
            success = await container.admin_service.mute_user(
                bot=callback.bot,
                group_id=chat_id,
                user_id=target_id,
                admin_id=admin_id,
                duration=duration,
                reason="(via /actions)"
            )
        elif action == "unmute":
            success = await container.admin_service.unmute_user(
                bot=callback.bot,
                group_id=chat_id,
                user_id=target_id,
                admin_id=admin_id
            )
        elif action == "warn":
            warns, limit = await container.admin_service.warn_user(
                group_id=chat_id,
                user_id=target_id,
                admin_id=admin_id,
                reason="(via /actions)"
            )
            success = True
            await callback.message.answer(
                f"⚠️ Warned user {target_id} ({warns}/{limit})."
            )
        elif action == "purge":
            # Simple purge: delete last N messages from the chat (not scoped to user_id here)
            count = min(duration or 0, 50)
            if count <= 0:
                await callback.answer("Invalid purge count", show_alert=True)
                return
            deleted = 0
            try:
                # Telegram API does not allow arbitrary history deletion via bot without message ids.
                # Placeholder: inform admin this needs message IDs; in future, track recent msgs.
                await callback.answer("Purge by count not supported without tracking messages.", show_alert=True)
                return
            except Exception as e:
                logger.error(f"Failed to purge messages: {e}")
                success = False
        else:
            await callback.answer("Unknown action", show_alert=True)
            return
        
        if success:
            await callback.answer("Done.")
        else:
            await callback.answer("Failed. Check bot/admin permissions.", show_alert=True)
