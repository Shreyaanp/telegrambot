"""Member event handlers for group management."""
import logging
from aiogram import Router, F
from aiogram.types import ChatMemberUpdated, Message
from aiogram.filters import ChatMemberUpdatedFilter, MEMBER, RESTRICTED, LEFT, KICKED

from bot.services.verification import VerificationService
from bot.services.user_manager import UserManager
from bot.utils.messages import group_welcome_message
from bot.config import Config

logger = logging.getLogger(__name__)

router = Router()


async def on_new_member(
    event: ChatMemberUpdated,
    user_manager: UserManager,
    verification_service: VerificationService,
    config: Config
):
    """
    Handle new member joining a group.
    
    This is triggered when someone joins or is added to the group.
    """
    new_member = event.new_chat_member.user
    chat = event.chat
    
    # Skip if it's the bot itself
    if new_member.is_bot:
        logger.info(f"Bot {new_member.username} added to group {chat.id}")
        return
    
    user_id = new_member.id
    username = new_member.username
    group_id = chat.id
    group_name = chat.title or "this group"
    
    logger.info(f"New member {user_id} ({username}) joined group {group_id}")
    
    # Check if already verified
    is_verified = await user_manager.is_verified(user_id)
    
    if is_verified:
        logger.info(f"User {user_id} is already verified, no action needed")
        return
    
    try:
        # Restrict the user (mute them)
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
        logger.info(f"Restricted user {user_id} in group {group_id}")
        
        # Send welcome message in group
        welcome_msg = group_welcome_message(group_name, config.verification_timeout)
        await event.bot.send_message(
            chat_id=group_id,
            text=welcome_msg,
            parse_mode="Markdown"
        )
        
        # Start verification flow (send DM)
        await verification_service.start_verification(
            bot=event.bot,
            telegram_id=user_id,
            chat_id=user_id,  # Send DM to user
            username=username,
            group_id=group_id
        )
        
    except Exception as e:
        logger.error(f"Error handling new member: {e}", exc_info=True)


def register_member_handlers(router: Router):
    """Register all member event handlers."""
    # Listen for new members joining
    router.chat_member.register(
        on_new_member,
        ChatMemberUpdatedFilter(member_status_changed=(LEFT | KICKED) >> (MEMBER | RESTRICTED))
    )

