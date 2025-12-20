"""Message handlers - intercept and process regular messages."""
import logging
import re
from aiogram import Router, F
from aiogram.types import Message

from bot.container import ServiceContainer
from aiogram.enums import ContentType

logger = logging.getLogger(__name__)
_URL_RE = re.compile(r"(https?://|www\.|t\.me/)", re.IGNORECASE)


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
        # Skip private chats
        if message.chat.type == "private":
            return

        group_id = message.chat.id
        text = message.text or ""

        # Enforce locks first (even for sender_chat / anonymous-admin style messages).
        lock_links, _lock_media = await container.lock_service.get_locks(group_id)
        logger.info(f"🔗 Lock check: group={group_id}, lock_links={lock_links}, lock_media={_lock_media}")
        
        is_anonymous_admin = (
            message.from_user is None
            and getattr(message, "sender_chat", None) is not None
            and int(message.sender_chat.id) == int(message.chat.id)
        )

        if lock_links and not is_anonymous_admin:
            has_url_entity = any(getattr(e, "type", None) in ("url", "text_link") for e in (message.entities or []))
            looks_like_url = bool(_URL_RE.search(text))
            logger.info(f"🔗 URL check: has_entity={has_url_entity}, looks_like_url={looks_like_url}, text={text[:50]}")
            if has_url_entity or looks_like_url:
                try:
                    await message.delete()
                    logger.info(f"🔗 Deleted message with link in group {group_id}")
                    return
                except Exception as e:
                    logger.debug(f"Failed to delete locked link message: {e}")

        # Anonymous admin / channel-post style messages have no from_user; skip everything else safely.
        if not message.from_user:
            return

        # Skip if from bot
        if message.from_user.is_bot:
            return

        # Don't treat commands as regular text content (avoid antiflood/filters on /commands)
        if text.startswith("/"):
            return
        
        user_id = message.from_user.id

        # Keep a lightweight per-group username→id mapping for @username moderation flows.
        try:
            await container.pending_verification_service.touch_group_user_throttled(
                group_id,
                user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                source="message",
            )
        except Exception:
            pass
        
        # ========== ANTI-FLOOD CHECK ==========
        is_flooding, msg_count, msg_ids_to_delete, flood_settings = await container.antiflood_service.check_flood(
            group_id=group_id,
            user_id=user_id,
            message_id=message.message_id
        )
        
        logger.info(f"🌊 Anti-flood check: group={group_id}, user={user_id}, flooding={is_flooding}, count={msg_count}, limit={flood_settings.get('limit', 10)}")
        
        if is_flooding:
            try:
                silent = flood_settings.get("silent", False)
                mute_seconds = flood_settings.get("mute_seconds", 300)
                action = flood_settings.get("action", "mute")
                delete_messages = flood_settings.get("delete_messages", True)
                warn_threshold = flood_settings.get("warn_threshold", 0)
                
                # Get current warning count
                warning_count = await container.antiflood_service.get_warning_count(group_id, user_id)
                
                # Delete all flood messages if enabled
                if delete_messages and msg_ids_to_delete:
                    deleted_count = 0
                    for msg_id in msg_ids_to_delete:
                        try:
                            await message.bot.delete_message(chat_id=group_id, message_id=msg_id)
                            deleted_count += 1
                        except Exception as e:
                            logger.debug(f"Failed to delete flood message {msg_id}: {e}")
                    
                    if deleted_count > 0:
                        logger.info(f"🗑️ Deleted {deleted_count} flood messages from user {user_id} in group {group_id}")
                    
                    # Clear tracked message IDs
                    await container.antiflood_service.clear_message_ids(group_id, user_id)
                
                # Check if we should warn first or take action
                should_take_action = warn_threshold == 0 or warning_count > warn_threshold
                
                if not should_take_action:
                    # Just warn the user
                    if not silent:
                        remaining_warnings = warn_threshold - warning_count + 1
                        await message.answer(
                            f"⚠️ {message.from_user.mention_html()}, please slow down! You're sending messages too quickly.\n\n"
                            f"⏳ {remaining_warnings} warning(s) remaining.",
                            parse_mode="HTML"
                        )
                    logger.info(f"Warned user {user_id} for flooding ({warning_count}/{warn_threshold} warnings)")
                    return
                
                # Take action based on configured action type
                action_taken = ""
                
                if action == "mute":
                    await container.admin_service.mute_user(
                        bot=message.bot,
                        group_id=group_id,
                        user_id=user_id,
                        admin_id=message.bot.id,
                        duration=mute_seconds,
                        reason=f"Flooding ({msg_count} messages)"
                    )
                    mins = max(1, int(round(mute_seconds / 60)))
                    action_taken = f"muted for {mins} minutes"
                    
                elif action == "warn":
                    await container.admin_service.warn_user(
                        bot=message.bot,
                        group_id=group_id,
                        user_id=user_id,
                        admin_id=message.bot.id,
                        reason=f"Flooding ({msg_count} messages)"
                    )
                    action_taken = "warned"
                    
                elif action == "kick":
                    await message.bot.ban_chat_member(chat_id=group_id, user_id=user_id)
                    await message.bot.unban_chat_member(chat_id=group_id, user_id=user_id)
                    action_taken = "kicked"
                    
                elif action == "ban":
                    await message.bot.ban_chat_member(chat_id=group_id, user_id=user_id)
                    action_taken = "banned"

                if not silent and action_taken:
                    await message.answer(
                        f"🚫 {message.from_user.mention_html()} has been {action_taken} for sending messages too quickly.",
                        parse_mode="HTML"
                    )
                
                logger.warning(f"Anti-flood action '{action}' taken on user {user_id} in group {group_id}")
                return
                
            except Exception as e:
                logger.error(f"Failed to handle flooding user: {e}")

        # ========== RULES ENGINE ==========
        try:
            match = await container.rules_service.apply_group_text_rules(
                message=message,
                admin_service=container.admin_service,
                sequence_service=container.sequence_service,
                ticket_service=container.ticket_service,
            )
            if match and match.stop_processing:
                return
        except Exception as e:
            logger.debug(f"Rules engine error: {e}")
        
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
                        bot=message.bot,
                        group_id=group_id,
                        user_id=user_id,
                        admin_id=message.bot.id,
                        reason=f"Triggered filter: {matched_filter.keyword}"
                    )
                    silent = False
                    try:
                        group = await container.group_service.get_or_create_group(group_id)
                        silent = bool(getattr(group, "silent_automations", False))
                    except Exception:
                        silent = False

                    if not silent:
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

    @router.message(F.caption)
    async def handle_caption_link_lock(message: Message):
        """
        Enforce link locks for captions (e.g. photo/video/document captions).
        """
        logger.info(f"📝 Caption handler triggered: group={message.chat.id}, content_type={str(message.content_type)}")
        
        if message.chat.type == "private":
            logger.debug(f"📝 Skipping private chat")
            return
            
        lock_links, _lock_media = await container.lock_service.get_locks(message.chat.id)
        logger.info(f"📝 Caption lock check: group={message.chat.id}, lock_links={lock_links}")
        
        if not lock_links:
            logger.debug(f"📝 Link locks disabled, skipping")
            return
            
        is_anonymous_admin = (
            message.from_user is None
            and getattr(message, "sender_chat", None) is not None
            and int(message.sender_chat.id) == int(message.chat.id)
        )
        if is_anonymous_admin:
            logger.debug(f"📝 Skipping anonymous admin message")
            return
            
        caption = message.caption or ""
        has_url_entity = any(getattr(e, "type", None) in ("url", "text_link") for e in (message.caption_entities or []))
        looks_like_url = bool(_URL_RE.search(caption))
        logger.info(f"📝 Caption URL check: has_entity={has_url_entity}, looks_like_url={looks_like_url}, caption={caption[:50]}")
        
        if has_url_entity or looks_like_url:
            try:
                await message.delete()
                logger.info(f"📝 ✅ Deleted captioned media with link in group {message.chat.id}")
            except Exception as e:
                logger.warning(f"📝 ❌ Failed to delete locked caption link message: {e}")

    @router.message(
        F.content_type.in_(
            {
                ContentType.PHOTO,
                ContentType.VIDEO,
                ContentType.DOCUMENT,
                ContentType.ANIMATION,
                ContentType.AUDIO,
                ContentType.VOICE,
                ContentType.VIDEO_NOTE,
                ContentType.STICKER,
                ContentType.CONTACT,
                ContentType.LOCATION,
                ContentType.VENUE,
                ContentType.POLL,
                ContentType.DICE,
            }
        )
    )
    async def handle_media_lock(message: Message):
        """
        Enforce media locks: delete media if lock_media is enabled.
        """
        logger.info(f"📷 Media handler triggered: group={message.chat.id}, content_type={str(message.content_type)}, user={message.from_user.id if message.from_user else 'None'}")
        
        if message.chat.type == "private":
            logger.debug(f"📷 Skipping private chat")
            return
            
        is_anonymous_admin = (
            message.from_user is None
            and getattr(message, "sender_chat", None) is not None
            and int(message.sender_chat.id) == int(message.chat.id)
        )
        if is_anonymous_admin:
            logger.debug(f"📷 Skipping anonymous admin message")
            return
            
        if message.from_user and not message.from_user.is_bot:
            try:
                await container.pending_verification_service.touch_group_user_throttled(
                    int(message.chat.id),
                    int(message.from_user.id),
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name,
                    source="message",
                )
            except Exception:
                pass
                
        _, lock_media = await container.lock_service.get_locks(message.chat.id)
        logger.info(f"📷 Media lock check: group={message.chat.id}, lock_media={lock_media}")
        
        if lock_media:
            try:
                await message.delete()
                logger.info(f"📷 ✅ Deleted media due to lock in group {message.chat.id}")
            except Exception as e:
                logger.warning(f"📷 ❌ Failed to delete locked media: {e}")
            return
        else:
            logger.debug(f"📷 Media locks disabled, allowing media")
        # No further processing for media here
    
    return router
