"""Member event handlers for group management - simplified."""
import logging
from aiogram import Router
from aiogram.types import ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, MEMBER, RESTRICTED, LEFT, KICKED

from bot.container import ServiceContainer
from bot.utils.messages import group_welcome_message
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
# send_perm_check imported lazily inside callback to avoid circular imports

logger = logging.getLogger(__name__)

router = Router()


def create_member_handlers(container: ServiceContainer) -> Router:
    """
    Create member event handlers with dependency injection.
    
    Args:
        container: Service container with all dependencies
        
    Returns:
        Router with registered handlers
    """
    router = Router()
    
    @router.chat_member(
        ChatMemberUpdatedFilter(
            member_status_changed=(LEFT | KICKED) >> (MEMBER | RESTRICTED)
        )
    )
    async def on_new_member(event: ChatMemberUpdated):
        """
        Handle new member joining a group.
        
        Flow:
        1. Check if user is already verified (global verification)
        2. If not, mute them immediately
        3. Send welcome message in group
        4. Send verification prompt in DM
        5. Start polling for verification status
        """
        new_member = event.new_chat_member.user
        chat = event.chat
        
        # Skip if it's a bot
        if new_member.is_bot:
            logger.info(f"Bot @{new_member.username} added to group {chat.id} ({chat.title})")
            return
        
        user_id = new_member.id
        username = new_member.username
        group_id = chat.id
        group_name = chat.title or "this group"
        
        logger.info(f"👤 New member: {user_id} (@{username}) joined group {group_id} ({group_name})")
        
        # Register group name/settings
        await container.group_service.register_group(group_id, group_name)
        
        # Load group settings
        group = await container.group_service.get_or_create_group(group_id)
        if not group.verification_enabled:
            logger.info(f"Verification disabled for group {group_id}; allowing user {user_id}")
            return
        
        timeout_seconds = group.verification_timeout or container.config.verification_timeout
        action_on_timeout = "kick" if group.kick_unverified else "mute"
        
        # Check if already verified globally
        is_verified = await container.user_manager.is_verified(user_id)
        
        if is_verified:
            logger.info(f"✅ User {user_id} is already verified globally, allowing access")
            return
        
        try:
            # Step 1: Mute the user immediately
            await event.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions={
                    "can_send_messages": False,
                    "can_send_media_messages": False,
                    "can_send_polls": False,
                    "can_send_other_messages": False,
                    "can_add_web_page_previews": False,
                }
            )
            logger.info(f"🔇 Muted user {user_id} in group {group_id}")
            
            # Step 2: Send welcome message in group (if configured)
            if group.welcome_enabled:
                welcome_msg = group_welcome_message(
                    group_name,
                    timeout_seconds
                )
                await event.bot.send_message(
                    chat_id=group_id,
                    text=welcome_msg,
                    parse_mode="Markdown"
                )
                logger.info(f"📨 Sent welcome message in group {group_id}")
            else:
                # Post a minimal setup hint for admins on first interactions
                manage_link = None
                bot_info = await event.bot.get_me()
                if bot_info.username:
                    manage_link = f"https://t.me/{bot_info.username}?start=menu-{group_id}"
                if manage_link:
                    await event.bot.send_message(
                        chat_id=group_id,
                        text="ℹ️ Manage verification and settings in DM.\nTap below to open the panel.",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[[InlineKeyboardButton(text="Open settings in DM", url=manage_link)]]
                        )
                    )
            
            # Step 3: Start verification flow (sends DM to user)
            success = await container.verification_service.start_verification(
                bot=event.bot,
                telegram_id=user_id,
                chat_id=user_id,  # Send DM to user
                username=username,
                group_id=group_id
            )
            
            if success:
                logger.info(f"✅ Started verification for user {user_id} in group {group_id}")
            else:
                logger.error(f"❌ Failed to start verification for user {user_id}")
                # User remains muted, they can try /verify manually
            
        except Exception as e:
            logger.error(f"❌ Error handling new member {user_id}: {e}", exc_info=True)
            
            # Try to notify the user in the group
            try:
                await event.bot.send_message(
                    chat_id=group_id,
                    text=f"⚠️ Error starting verification for @{username}. Please try `/verify` in a private message with me.",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    return router


def create_admin_join_handlers(container: ServiceContainer) -> Router:
    """
    Separate router for bot-added-to-group / admin setup message.
    """
    router = Router()
    
    @router.chat_member(
        ChatMemberUpdatedFilter(
            member_status_changed=LEFT >> MEMBER
        )
    )
    async def on_bot_added(event: ChatMemberUpdated):
        """
        When the bot is added to a group, post a setup card for admins.
        """
        if not event.new_chat_member.user.is_bot:
            return
        
        group_id = event.chat.id
        group_name = event.chat.title or "this group"
        
        # Register group
        await container.group_service.register_group(group_id, group_name)
        
        bot_info = await event.bot.get_me()
        manage_link = f"https://t.me/{bot_info.username}?start=menu-{group_id}"
        
        setup_text = (
            f"👋 Thanks for adding me to *{group_name}*!\n\n"
            "To work properly, please:\n"
            "1) Promote me to *Admin*.\n"
            "2) Grant *Restrict Members* and *Delete Messages* (Pin optional).\n"
            "3) Run `/menu` in this group to open settings in DM.\n\n"
            "You can also tap below to open the DM panel."
        )
        await event.bot.send_message(
            chat_id=group_id,
            text=setup_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Open settings in DM", url=manage_link)],
                    [InlineKeyboardButton(text="Check permissions", callback_data=f"checkperms:{group_id}")]
                ]
            )
        )
    
    return router
