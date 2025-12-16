"""Message handlers - intercept and process regular messages."""
import logging
from aiogram import Router, F
from aiogram.types import Message

from bot.container import ServiceContainer
from aiogram.enums import ContentType

logger = logging.getLogger(__name__)


def create_message_handlers(container: ServiceContainer) -> Router:
    """
    Create message handlers for filtering, antiflood, and hashtag notes.
    
    Args:
        container: Service container with all dependencies
        
    Returns:
        Router with registered handlers
    """
    router = Router()
    
    @router.message(F.text)
    async def handle_text_message(message: Message):
        """
        Handle all text messages for:
        - Anti-flood detection
        - Message filters
        - Hashtag notes (#notename)
        """
        # Skip if from bot or in private chat
        if message.from_user.is_bot or message.chat.type == "private":
            return

        # Don't treat commands as regular text content (avoid antiflood/filters on /commands)
        if message.text and message.text.startswith("/"):
            return
        
        group_id = message.chat.id
        user_id = message.from_user.id
        text = message.text
        
        # Enforce locks: links
        lock_links, lock_media = await container.lock_service.get_locks(group_id)
        if lock_links and ("http://" in text or "https://" in text):
            try:
                await message.delete()
                return
            except Exception as e:
                logger.debug(f"Failed to delete locked link message: {e}")
        
        # Enforce media lock (non-text messages handled separately below)
        if lock_media:
            # If text contains media indicators, skip; media enforcement happens in another handler
            pass
        
        # ========== ANTI-FLOOD CHECK ==========
        is_flooding, msg_count = await container.antiflood_service.check_flood(
            group_id=group_id,
            user_id=user_id
        )
        
        if is_flooding:
            # Mute the user for flooding
            try:
                await container.admin_service.mute_user(
                    bot=message.bot,
                    group_id=group_id,
                    user_id=user_id,
                    admin_id=message.bot.id,
                    duration=300,  # 5 minutes
                    reason=f"Flooding ({msg_count} messages)"
                )
                
                # Delete the flood message
                try:
                    await message.delete()
                except:
                    pass
                
                # Warn them
                await message.answer(
                    f"🚫 {message.from_user.mention_html()} has been muted for 5 minutes due to flooding.\n\n"
                    f"📊 Sent {msg_count} messages too quickly.",
                    parse_mode="HTML"
                )
                
                logger.warning(f"Muted user {user_id} for flooding in group {group_id}")
                return
                
            except Exception as e:
                logger.error(f"Failed to mute flooding user: {e}")
        
        # ========== CHECK FILTERS ==========
        matched_filter = await container.filter_service.check_filters(group_id, text)
        
        if matched_filter:
            if matched_filter.filter_type == "delete":
                # Delete the message
                try:
                    await message.delete()
                    logger.info(f"Deleted message matching filter '{matched_filter.keyword}'")
                except Exception as e:
                    logger.error(f"Failed to delete message: {e}")
                return
            
            elif matched_filter.filter_type == "warn":
                # Warn the user
                try:
                    await container.admin_service.warn_user(
                        group_id=group_id,
                        user_id=user_id,
                        admin_id=message.bot.id,
                        reason=f"Triggered filter: {matched_filter.keyword}"
                    )
                    await message.reply(
                        f"⚠️ Warning: {matched_filter.response}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Failed to warn user: {e}")
                return
            
            else:  # text response
                # Send the response
                try:
                    await message.reply(matched_filter.response, parse_mode="Markdown")
                    logger.info(f"Responded to filter '{matched_filter.keyword}'")
                except Exception as e:
                    logger.error(f"Failed to send filter response: {e}")
                return
        
        # ========== CHECK FOR HASHTAG NOTES ==========
        if text.startswith("#"):
            # Extract note name (first word after #)
            note_name = text[1:].split()[0].lower() if len(text) > 1 else None
            
            if note_name:
                note = await container.notes_service.get_note(group_id, note_name)
                
                if note:
                    try:
                        await message.reply(note.content, parse_mode="Markdown")
                        logger.info(f"Sent note '{note_name}' in group {group_id}")
                    except Exception as e:
                        logger.error(f"Failed to send note: {e}")
    
    @router.message(F.content_type.in_({ContentType.PHOTO, ContentType.VIDEO, ContentType.DOCUMENT, ContentType.ANIMATION, ContentType.AUDIO, ContentType.VOICE, ContentType.VIDEO_NOTE, ContentType.STICKER}))
    async def handle_media_lock(message: Message):
        """
        Enforce media locks: delete media if lock_media is enabled.
        """
        if message.chat.type == "private":
            return
        _, lock_media = await container.lock_service.get_locks(message.chat.id)
        if lock_media:
            try:
                await message.delete()
                logger.info(f"Deleted media due to lock in group {message.chat.id}")
            except Exception as e:
                logger.debug(f"Failed to delete locked media: {e}")
            return
        # No further processing for media here
    
    return router
