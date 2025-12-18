"""Admin command handlers - kick, ban, warn, whitelist, settings."""
import logging
from html import escape
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from bot.container import ServiceContainer
from bot.utils.permissions import (
    require_restrict_permission,
    require_admin,
    require_role_or_admin,
    require_telegram_admin,
    can_user,
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
from database.db import db
from database.models import User, VerificationSession, PendingJoinVerification, Group
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

def _reason_line(reason: str | None) -> str:
    if not reason:
        return ""
    return f"\nReason: {escape(reason)}"

def _parse_duration_token(token: str) -> int | None:
    """
    Parse a duration token like "30s", "10m", "2h", "1d", or raw seconds ("600").
    Returns seconds or None if token isn't a duration.
    """
    t = (token or "").strip().lower()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    if len(t) < 2:
        return None
    num, unit = t[:-1], t[-1]
    if not num.isdigit():
        return None
    n = int(num)
    if unit == "s":
        return n
    if unit == "m":
        return n * 60
    if unit == "h":
        return n * 3600
    if unit == "d":
        return n * 86400
    return None


def create_admin_handlers(container: ServiceContainer) -> Router:
    """
    Create admin command handlers.
    
    Args:
        container: Service container with all dependencies
        
    Returns:
        Router with registered handlers
    """
    router = Router()
    
    # ========== INLINE MODE: OPTIONAL PREFILL COMMANDS ==========
    #
    # Optional convenience for admins to generate clickable prefilled commands via inline queries.
    # Requires enabling inline mode in @BotFather, but the bot works without it.
    @router.inline_query()
    async def inline_prefill(inline_query: InlineQuery):
        raw = (inline_query.query or "").strip()
        parts = raw.split(maxsplit=2)
        if not parts:
            results = [
                InlineQueryResultArticle(
                    id="help",
                    title="Commands",
                    description="Type: kick|ban|mute|unmute|warn <user_id> [reason]",
                    input_message_content=InputTextMessageContent(
                        message_text="kick <user_id> [reason]\nban <user_id> [reason]\nmute <user_id> [reason]\nunmute <user_id>\nwarn <user_id> [reason]",
                        parse_mode=None,
                    ),
                )
            ]
            await inline_query.answer(results, cache_time=1, is_personal=True)
            return

        action = parts[0].lower()
        target = parts[1] if len(parts) > 1 else ""
        rest = parts[2] if len(parts) > 2 else ""

        supported = {"kick", "ban", "mute", "unmute", "warn", "unban"}
        if action not in supported:
            await inline_query.answer(
                [
                    InlineQueryResultArticle(
                        id="unsupported",
                        title="Unsupported action",
                        description="Use: kick|ban|mute|unmute|warn|unban",
                        input_message_content=InputTextMessageContent(message_text="/help", parse_mode=None),
                    )
                ],
                cache_time=1,
                is_personal=True,
            )
            return

        if not target:
            await inline_query.answer(
                [
                    InlineQueryResultArticle(
                        id="missing_target",
                        title=f"/{action} <user_id> [reason]",
                        description="Missing user id/username",
                        input_message_content=InputTextMessageContent(message_text=f"/{action} <user_id> ", parse_mode=None),
                    )
                ],
                cache_time=1,
                is_personal=True,
            )
            return

        # Prefer numeric IDs, but allow @username as a best-effort convenience.
        cmd = f"/{action} {target}"
        if rest:
            cmd = f"{cmd} {rest}"

        title = f"Send {cmd}"
        desc = "Sends the command into this chat"
        result = InlineQueryResultArticle(
            id=f"{action}:{target}"[:64],
            title=title[:256],
            description=desc[:512],
            input_message_content=InputTextMessageContent(message_text=cmd, parse_mode=None),
        )
        await inline_query.answer([result], cache_time=1, is_personal=True)

    # ========== MODERATION COMMANDS ==========
    
    @router.message(Command("kick", "vkick"))
    @require_restrict_permission(action="kick")
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
            await message.answer(
                f"<b>✅ User Kicked</b>\n\n"
                f"👤 User: {escape(user_mention)}\n"
                f"👮 Admin: {message.from_user.mention_html()}"
                f"{_reason_line(reason)}",
                parse_mode="HTML",
            )
        else:
            await message.answer("❌ Failed to kick user. Make sure I have admin rights.")

    @router.message(Command("actions"))
    async def cmd_actions(message: Message):
        """
        Show admin actions for the replied user.
        
        Usage: reply to a user's message with /actions
        """
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply("❌ This command only works in groups.")
            return

        # Allow Telegram admins OR role users who can warn/kick.
        if not (await can_user(message.bot, message.chat.id, message.from_user.id, "warn") or await can_user(message.bot, message.chat.id, message.from_user.id, "kick")):
            await message.reply("❌ Not allowed.")
            return

        if not await is_bot_admin(message.bot, message.chat.id):
            await message.reply("❌ I need to be an admin to do this.")
            return

        if not message.reply_to_message:
            await message.reply("Reply to a user's message with /actions to manage them.")
            return
        
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.full_name if message.reply_to_message.from_user else str(target_id)
        text = f"<b>Actions</b>\nTarget: {target_name} (<code>{target_id}</code>)"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Warn", callback_data=f"act:warn:{target_id}:0"),
                    InlineKeyboardButton(text="Kick…", callback_data=f"act:confirm_kick:{target_id}:0"),
                    InlineKeyboardButton(text="Ban…", callback_data=f"act:confirm_ban:{target_id}:0"),
                ],
                [
                    InlineKeyboardButton(text="Mute 10m", callback_data=f"act:mute:{target_id}:600"),
                    InlineKeyboardButton(text="Mute 1h", callback_data=f"act:mute:{target_id}:3600"),
                    InlineKeyboardButton(text="Unmute", callback_data=f"act:unmute:{target_id}:0"),
                ],
                [
                    InlineKeyboardButton(text="Tempban 1h", callback_data=f"act:tempban:{target_id}:3600"),
                    InlineKeyboardButton(text="Tempban 24h", callback_data=f"act:tempban:{target_id}:86400"),
                ],
                [
                    InlineKeyboardButton(text="Purge…", callback_data=f"act:purge_menu:{target_id}:0"),
                ],
                [
                    InlineKeyboardButton(text="Close", callback_data=f"act:close:{target_id}:0"),
                ],
            ]
        )
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    
    @router.message(Command("ban", "vban"))
    @require_restrict_permission(action="ban")
    async def cmd_ban(message: Message):
        """
        Ban a user from the group.
        
        Usage:
            /ban (reply to user) [reason]
            /ban @username [reason]
        """
        # Support: /ban <user> [duration] [reason]
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
        
        # Try to parse optional duration from raw text (extract_user_and_reason doesn't handle it).
        until_date = None
        parts = (message.text or "").split()
        if len(parts) >= 3:
            seconds = _parse_duration_token(parts[2])
            if seconds is not None:
                from datetime import datetime, timedelta
                until_date = datetime.utcnow() + timedelta(seconds=seconds)
                # If reason was parsed as "duration rest...", strip the duration token.
                if reason:
                    reason_parts = reason.split(maxsplit=1)
                    if reason_parts and _parse_duration_token(reason_parts[0]) is not None:
                        reason = reason_parts[1] if len(reason_parts) > 1 else None

        # Ban the user
        success = await container.admin_service.ban_user(
            bot=message.bot,
            group_id=message.chat.id,
            user_id=user_id,
            admin_id=message.from_user.id,
            reason=reason,
            until_date=until_date,
        )
        await container.metrics_service.incr_admin_action("ban", message.chat.id)
        
        if success:
            user_mention = await get_user_mention(message, user_id)
            await message.answer(
                f"<b>🚫 User Banned</b>\n\n"
                f"👤 User: {escape(user_mention)}\n"
                f"👮 Admin: {message.from_user.mention_html()}"
                f"{_reason_line(reason)}\n\n"
                f"💡 Use <code>/unban</code> to lift the ban",
                parse_mode="HTML",
            )
        else:
            await message.answer("❌ Failed to ban user. Make sure I have admin rights.")
    
    @router.message(Command("unban", "vunban"))
    @require_restrict_permission(action="ban")
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
            await message.answer(f"✅ User <code>{user_id}</code> has been unbanned.", parse_mode="HTML")
        else:
            await message.answer("❌ Failed to unban user.")
    
    @router.message(Command("mute"))
    @require_restrict_permission(action="kick")
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
        
        # Support: /mute <user> [duration] [reason]
        duration = None
        parts = (message.text or "").split()
        if len(parts) >= 3:
            seconds = _parse_duration_token(parts[2])
            if seconds is not None:
                duration = seconds
                if reason:
                    reason_parts = reason.split(maxsplit=1)
                    if reason_parts and _parse_duration_token(reason_parts[0]) is not None:
                        reason = reason_parts[1] if len(reason_parts) > 1 else None

        success = await container.admin_service.mute_user(
            bot=message.bot,
            group_id=message.chat.id,
            user_id=user_id,
            admin_id=message.from_user.id,
            duration=duration,
            reason=reason,
        )
        await container.metrics_service.incr_admin_action("mute", message.chat.id)
        
        if success:
            user_mention = await get_user_mention(message, user_id)
            duration_text = format_time_delta(duration) if duration else "Permanent"
            await message.answer(
                f"<b>🔇 User Muted</b>\n\n"
                f"👤 User: {escape(user_mention)}\n"
                f"👮 Admin: {message.from_user.mention_html()}"
                f"\n⏱ Duration: {escape(duration_text)}"
                f"{_reason_line(reason)}\n\n"
                f"💡 Use <code>/unmute</code> to restore their voice",
                parse_mode="HTML",
            )
        else:
            await message.answer("❌ Failed to mute user.")
    
    @router.message(Command("unmute"))
    @require_restrict_permission(action="kick")
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
            await message.answer(
                f"<b>🔊 User Unmuted</b>\n\n👤 {escape(user_mention)} can now speak again!",
                parse_mode="HTML",
            )
        else:
            await message.answer("❌ Failed to unmute user.")

    @router.message(Command("purge"))
    @require_restrict_permission(action="kick")
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
        max_delete = 50
        if end_id - start_id + 1 > max_delete:
            await message.reply(
                f"Too many messages ({end_id - start_id + 1}). For safety, I only purge up to {max_delete} at a time.\n"
                f"Tip: use /actions → Purge… for a bounded purge.",
                parse_mode="HTML",
            )
            return
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
    @require_role_or_admin("warn")
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
            bot=message.bot,
            group_id=message.chat.id,
            user_id=user_id,
            admin_id=message.from_user.id,
            reason=reason,
        )
        await container.metrics_service.incr_admin_action("warn", message.chat.id)
        
        user_mention = await get_user_mention(message, user_id)
        reason_line = _reason_line(reason)
        
        if warn_count >= warn_limit:
            # Auto-kick on limit reached
            await container.admin_service.kick_user(
                bot=message.bot,
                group_id=message.chat.id,
                user_id=user_id,
                admin_id=message.from_user.id,
                reason=f"Reached warning limit ({warn_limit} warnings)"
            )
            await message.answer(
                f"<b>⚠️ Warning Limit Reached</b>\n\n"
                f"👤 User: {escape(user_mention)}\n"
                f"📊 Warnings: {warn_count}/{warn_limit}"
                f"{reason_line}\n\n"
                f"🚫 User has been kicked from the group.",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"<b>⚠️ User Warned</b>\n\n"
                f"👤 User: {escape(user_mention)}\n"
                f"👮 Admin: {message.from_user.mention_html()}\n"
                f"📊 Warnings: {warn_count}/{warn_limit}"
                f"{reason_line}\n\n"
                f"💡 Use <code>/warns</code> to check warnings",
                parse_mode="HTML",
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
    @require_role_or_admin("verify")
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
    @require_role_or_admin("verify")
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
    async def cmd_checkperms(message: Message):
        """Check bot and your permissions in this group."""
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply("❌ This command only works in groups.")
            return
        if not await is_user_admin(message.bot, message.chat.id, message.from_user.id):
            if not await has_role_permission(message.chat.id, message.from_user.id, "settings"):
                await message.reply("❌ Not allowed.")
                return
        await send_perm_check(message.bot, message.chat.id, message.from_user.id, reply_to=message)

    @router.message(Command("status"))
    async def cmd_status(message: Message):
        """Admin-only status summary."""
        if message.chat.type not in ["group", "supergroup"]:
            return
        if not await can_user(message.bot, message.chat.id, message.from_user.id, "status"):
            await message.reply("Not allowed.", parse_mode="HTML")
            return
        container_obj = container
        admin_actions, verification_outcomes, api_errors, last_update_at = await container_obj.metrics_service.snapshot()
        # DB-backed counts (stable across restarts)
        try:
            async with db.session() as session:
                user_count = (await session.execute(select(func.count(User.telegram_id)))).scalar() or 0
                active_sessions = (
                    (await session.execute(select(func.count(VerificationSession.session_id)).where(VerificationSession.status == "pending"))).scalar()
                    or 0
                )
                pending_joins = (
                    (await session.execute(select(func.count(PendingJoinVerification.id)).where(PendingJoinVerification.status == "pending"))).scalar()
                    or 0
                )
                group = (await session.execute(select(Group).where(Group.group_id == message.chat.id))).scalar_one_or_none()
        except Exception:
            user_count = active_sessions = pending_joins = 0
            group = None

        logs_dest = "Off"
        try:
            if group and getattr(group, "logs_enabled", False) and getattr(group, "logs_chat_id", None):
                logs_dest = str(int(group.logs_chat_id))
        except Exception:
            pass

        text = (
            "<b>Status</b>\n"
            f"last_update: {last_update_at.isoformat() if last_update_at else 'n/a'}\n"
            f"verified_users: {user_count}\n"
            f"active_sessions: {active_sessions}\n"
            f"pending_joins: {pending_joins}\n"
            f"logs_dest: {logs_dest}\n"
            f"actions: {sum(admin_actions.values())}\n"
            f"verifications: {verification_outcomes}\n"
            f"api_errors: {api_errors}\n"
        )
        await message.reply(text, parse_mode="HTML")
    
    # ========== SETTINGS ==========
    
    @router.message(Command("settings"))
    @require_role_or_admin("settings")
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
    @require_role_or_admin("locks")
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
    @require_role_or_admin("locks")
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
    @require_telegram_admin
    async def cmd_roles(message: Message):
        """
        Manage custom roles.
        Usage:
            /roles            -> list
            /roles add @user role   (role: moderator|helper|<custom>)
            /roles remove @user
            /roles show @user
            /roles set @user <perm> on|off
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
        elif action == "show":
            user_id, _ = await extract_user_and_reason(message)
            if not user_id:
                await message.reply("Reply to the user or provide their ID for /roles show.")
                return
            perm = await container.roles_service.get_role(message.chat.id, user_id)
            if not perm:
                await message.reply("ℹ️ No role found for that user.")
                return
            flags = container.roles_service.format_flags(perm)
            await message.reply(f"🧑‍💼 Role for `{user_id}`: *{perm.role}*\n{flags}", parse_mode="Markdown")
        elif action == "set" and len(parts) >= 5:
            user_id, _ = await extract_user_and_reason(message)
            if not user_id:
                await message.reply("Reply to the user or provide their ID for /roles set.")
                return
            perm_key = parts[3].lower()
            val = parts[4].lower()
            if val not in ("on", "off"):
                await message.reply("Value must be `on` or `off`.")
                return
            ok = await container.roles_service.set_permission(
                group_id=message.chat.id,
                user_id=user_id,
                permission_key=perm_key,
                enabled=(val == "on"),
                granted_by=message.from_user.id,
            )
            if not ok:
                await message.reply(
                    "Unknown permission. Use one of:\n"
                    "`verify`, `kick`, `ban`, `warn`, `notes`, `filters`, `settings`, `locks`, `roles`, `status`, `logs`",
                    parse_mode="Markdown",
                )
                return
            perm = await container.roles_service.get_role(message.chat.id, user_id)
            flags = container.roles_service.format_flags(perm) if perm else ""
            await message.reply(f"✅ Updated `{perm_key}` for `{user_id}`.\n{flags}", parse_mode="Markdown")
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
            await message.reply(
                "Usage:\n"
                "`/roles`\n"
                "`/roles add <user> moderator|helper|customname`\n"
                "`/roles show <user>`\n"
                "`/roles set <user> <perm> on|off`\n"
                "`/roles remove <user>`",
                parse_mode="Markdown",
            )
    
    @router.callback_query(lambda c: c.data and c.data.startswith("checkperms:"))
    async def checkperms_cb(callback: CallbackQuery):
        """Callback to check permissions from older setup cards."""
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

    @router.callback_query(lambda c: c.data and c.data.startswith("act:"))
    async def admin_action_callback(callback: CallbackQuery):
        """
        Handle admin actions invoked from /actions.
        Format: act:<action>:<target_id>:<duration_seconds>
        """
        data = callback.data.split(":")
        if len(data) != 4:
            await callback.answer("Invalid action", show_alert=True)
            return

        _, action, target_str, duration_str = data
        chat_id = callback.message.chat.id
        actor_id = callback.from_user.id

        async def target_display(uid: int) -> str:
            try:
                member = await callback.bot.get_chat_member(chat_id, uid)
                name = member.user.full_name
            except Exception:
                name = str(uid)
            return f"{name} (<code>{uid}</code>)"

        async def render_actions():
            text = f"<b>Actions</b>\nTarget: {await target_display(target_id)}"
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Warn", callback_data=f"act:warn:{target_id}:0")],
                    [
                        InlineKeyboardButton(text="Mute 10m", callback_data=f"act:mute:{target_id}:600"),
                        InlineKeyboardButton(text="Mute 1h", callback_data=f"act:mute:{target_id}:3600"),
                        InlineKeyboardButton(text="Mute 24h", callback_data=f"act:mute:{target_id}:86400"),
                    ],
                    [
                        InlineKeyboardButton(text="Kick", callback_data=f"act:confirm_kick:{target_id}:0"),
                        InlineKeyboardButton(text="Ban", callback_data=f"act:confirm_ban:{target_id}:0"),
                    ],
                    [InlineKeyboardButton(text="Purge…", callback_data=f"act:purge_menu:{target_id}:0")],
                    [InlineKeyboardButton(text="Close", callback_data=f"act:close:{target_id}:0")],
                ]
            )
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

        async def render_confirm(label: str, confirm_action: str, count: int = 0):
            text = f"<b>Confirm</b>\n{label} • {await target_display(target_id)}"
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Confirm", callback_data=f"act:{confirm_action}:{target_id}:{count}"),
                        InlineKeyboardButton(text="Cancel", callback_data=f"act:back:{target_id}:0"),
                    ]
                ]
            )
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

        # Permission checks: telegram admin OR custom role
        is_admin = await is_user_admin(callback.bot, chat_id, actor_id)
        if not is_admin:
            needed = "kick" if action in ("kick", "ban", "tempban", "mute", "unmute", "confirm_kick", "confirm_ban") else "warn"
            if action in ("purge_menu", "confirm_purge", "purge"):
                needed = "kick"
            if not await has_role_permission(chat_id, actor_id, needed):
                await callback.answer("Not allowed", show_alert=True)
                return

        if not await is_bot_admin(callback.bot, chat_id):
            await callback.answer("Bot not admin.", show_alert=True)
            return

        try:
            target_id = int(target_str)
            duration = int(duration_str)
        except ValueError:
            await callback.answer("Invalid target.", show_alert=True)
            return

        if action == "close":
            await callback.answer()
            try:
                await callback.message.edit_text("Closed.", parse_mode="HTML")
            except Exception:
                pass
            return
        if action == "back":
            await callback.answer()
            await render_actions()
            return
        if action == "confirm_kick":
            await callback.answer()
            await render_confirm("Kick", "kick")
            return
        if action == "confirm_ban":
            await callback.answer()
            await render_confirm("Ban", "ban")
            return
        if action == "purge_menu":
            await callback.answer()
            text = f"<b>Purge</b>\nTarget: {await target_display(target_id)}"
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Purge 10", callback_data=f"act:confirm_purge:{target_id}:10"),
                        InlineKeyboardButton(text="Purge 25", callback_data=f"act:confirm_purge:{target_id}:25"),
                        InlineKeyboardButton(text="Purge 50", callback_data=f"act:confirm_purge:{target_id}:50"),
                    ],
                    [InlineKeyboardButton(text="Back", callback_data=f"act:back:{target_id}:0")],
                ]
            )
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            return
        if action == "confirm_purge":
            await callback.answer()
            await render_confirm(f"Purge {duration}", "purge", count=duration)
            return

        # Actions requiring restrict need bot + actor capability
        if action in ("kick", "ban", "tempban", "mute", "unmute"):
            if not await can_restrict_members(callback.bot, chat_id, (await callback.bot.get_me()).id):
                await callback.answer("I need Restrict members.", show_alert=True)
                return

        success = False

        if action == "kick":
            success = await container.admin_service.kick_user(callback.bot, chat_id, target_id, actor_id, reason="(via /actions)")
        elif action == "ban":
            success = await container.admin_service.ban_user(callback.bot, chat_id, target_id, actor_id, reason="(via /actions)")
        elif action == "tempban":
            from datetime import datetime, timedelta

            until = datetime.utcnow() + timedelta(seconds=duration or 3600)
            success = await container.admin_service.ban_user(callback.bot, chat_id, target_id, actor_id, reason="(via /actions tempban)", until_date=until)
        elif action == "mute":
            success = await container.admin_service.mute_user(callback.bot, chat_id, target_id, actor_id, duration=duration, reason="(via /actions)")
        elif action == "unmute":
            success = await container.admin_service.unmute_user(callback.bot, chat_id, target_id, actor_id)
        elif action == "warn":
            warns, limit = await container.admin_service.warn_user(
                bot=callback.bot,
                group_id=chat_id,
                user_id=target_id,
                admin_id=actor_id,
                reason="(via /actions)",
            )
            success = True
            await callback.message.edit_text(f"⚠️ Warned {await target_display(target_id)} ({warns}/{limit}).", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Back", callback_data=f"act:back:{target_id}:0")]]))
        elif action == "purge":
            count = max(1, min(duration, 50))
            deleted = 0
            for i in range(count):
                mid = callback.message.message_id - i
                try:
                    await callback.bot.delete_message(chat_id=chat_id, message_id=mid)
                    deleted += 1
                except Exception:
                    pass
            success = deleted > 0
        else:
            await callback.answer("Unknown action", show_alert=True)
            return

        await container.metrics_service.incr_admin_action(action, chat_id)
        await callback.answer("Done." if success else "Failed.", show_alert=not success)
        if action in ("kick", "ban", "tempban", "mute", "unmute", "purge") and success:
            try:
                await callback.message.edit_text("✅ Done.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Back", callback_data=f"act:back:{target_id}:0")]]))
            except Exception:
                pass

    return router


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
    
    restrict = "✅" if getattr(bot_member, "can_restrict_members", False) else "❌"
    delete = "✅" if getattr(bot_member, "can_delete_messages", False) else "❌"
    pin = "✅" if getattr(bot_member, "can_pin_messages", False) else "◻️"
    invite = "✅" if (bot_member.status == "creator" or getattr(bot_member, "can_invite_users", False)) else "❌"

    try:
        chat = await bot.get_chat(chat_id)
        join_by_request = getattr(chat, "join_by_request", None)
        join_requests = "✅" if join_by_request is True else "❌"
    except Exception:
        join_requests = "❔"

    text = (
        "<b>Permissions</b>\n"
        f"Restrict: {restrict}  Delete: {delete}  Pin: {pin}\n"
        f"Join requests: {join_requests}  Invite users: {invite}\n\n"
        "Fix: promote bot + enable missing perms. Join gate needs Join requests + Invite users."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Re-check", callback_data=f"setup:recheck:{chat_id}")],
            [InlineKeyboardButton(text="Help", callback_data="setup:help")],
        ]
    )
    await reply_to.reply(text, parse_mode="HTML", reply_markup=kb)
