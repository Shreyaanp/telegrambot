"""Member event handlers for group management - simplified."""
import logging
import asyncio
from datetime import datetime, timedelta, timezone, timezone
from aiogram import Router
from aiogram.types import ChatMemberUpdated, CallbackQuery
from aiogram.filters import ChatMemberUpdatedFilter, MEMBER, RESTRICTED, LEFT, KICKED, ADMINISTRATOR, CREATOR
from aiogram import F

from bot.container import ServiceContainer
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import ChatPermissions

from bot.utils.permissions import can_user, is_user_admin, has_role_permission, is_bot_admin, can_restrict_members, can_delete_messages, can_pin_messages
from bot.utils.chat_permissions import get_chat_default_permissions
from database.db import db
from database.models import GroupWizardState
from sqlalchemy import select

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

    @router.chat_member(ChatMemberUpdatedFilter(member_status_changed=(MEMBER | RESTRICTED) >> (ADMINISTRATOR | CREATOR)))
    async def on_member_promoted(event: ChatMemberUpdated):
        """
        If a previously restricted/pending user is promoted to admin, stop verification enforcement.

        This prevents the UX where a newly promoted admin can't speak/use commands because they were in a pending gate.
        """
        user = event.new_chat_member.user
        if user.is_bot:
            return

        group_id = int(event.chat.id)
        user_id = int(user.id)

        # Cancel any active pending verification and remove the prompt (best-effort).
        try:
            pending = await container.pending_verification_service.get_active_for_user(group_id, user_id)
            if pending:
                bot_me = await event.bot.get_me()
                await container.pending_verification_service.decide(int(pending.id), status="cancelled", decided_by=int(bot_me.id))
                await container.pending_verification_service.delete_group_prompt(event.bot, pending)
        except Exception as e:
            logger.debug(f"Could not cancel pending verification for promoted user {user_id}: {e}")

        # Best-effort: restore send permissions (may fail for admins; that's fine).
        try:
            perms = await get_chat_default_permissions(event.bot, group_id)
            await event.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions=perms,
            )
        except Exception as e:
            logger.debug(f"Could not restore permissions for promoted user {user_id}: {e}")

    async def _send_welcome(bot, group_id: int, user) -> None:
        try:
            welcome = await container.welcome_service.get_welcome(group_id)
            if not welcome:
                return
            enabled, template, destination = welcome
            if not enabled or not template:
                return
            try:
                chat = await container.group_service.get_or_create_group(group_id)
                group_name = chat.group_name or "this group"
            except Exception as e:
                logger.debug(f"Could not get group name for {group_id}: {e}")
                group_name = "this group"
            try:
                member_count = await bot.get_chat_member_count(group_id)
            except Exception as e:
                logger.debug(f"Could not get member count for {group_id}: {e}")
                member_count = 0

            name = getattr(user, "full_name", None) or getattr(user, "first_name", None) or "there"
            try:
                mention = user.mention_html()
            except Exception as e:
                logger.debug(f"Could not create mention for user: {e}")
                mention = name
            text = container.welcome_service.format_message(template, name, mention, group_name, int(member_count or 0))
            
            # Send to group if destination is 'group' or 'both'
            if destination in ["group", "both"]:
                try:
                    await bot.send_message(chat_id=group_id, text=text, parse_mode="HTML")
                except Exception as e:
                    logger.debug(f"Could not send welcome message in group {group_id}: {e}")
            
            # Send to DM if destination is 'dm' or 'both'
            if destination in ["dm", "both"]:
                try:
                    user_id = getattr(user, "id", None)
                    if user_id:
                        await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
                except Exception as e:
                    logger.debug(f"Could not send welcome DM to user {user_id}: {e}")
        except Exception as e:
            logger.debug(f"Could not send welcome message in group {group_id}: {e}")
            return
    
    @router.chat_member(
        ChatMemberUpdatedFilter(
            member_status_changed=(LEFT | KICKED) >> (MEMBER | RESTRICTED)
        )
    )
    async def on_new_member(event: ChatMemberUpdated):
        """
        Handle new member joining a group.
        
        Flow:
        1) If verification disabled: do nothing
        2) If user globally verified: allow
        3) Else: restrict, post join prompt with expiring deep link and admin Approve/Reject
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
        await container.pending_verification_service.touch_group_user(
            group_id,
            user_id,
            username=username,
            first_name=new_member.first_name,
            last_name=new_member.last_name,
            source="join",
            increment_join=True,
        )
        
        # Load group settings
        group = await container.group_service.get_or_create_group(group_id)

        # Federation ban: block user if the group is part of a federation and the user is banned there.
        try:
            fed_id = getattr(group, "federation_id", None)
            if fed_id and await container.federation_service.is_banned(federation_id=int(fed_id), telegram_id=user_id):
                try:
                    bot_me = await event.bot.get_me()
                    await event.bot.ban_chat_member(chat_id=group_id, user_id=user_id)
                    await container.admin_service.log_custom_action(
                        event.bot,
                        group_id,
                        actor_id=int(bot_me.id),
                        target_id=int(user_id),
                        action="fed_ban_block",
                        reason=f"Federation ban (fed={int(fed_id)})",
                    )
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Anti-raid: if raid mode is active, block untrusted new joins.
        raid_until = getattr(group, "raid_mode_until", None)
        if raid_until and raid_until > datetime.utcnow():
            try:
                if await container.whitelist_service.is_whitelisted(group_id, user_id):
                    await _send_welcome(event.bot, group_id, new_member)
                    return
            except Exception:
                pass

            is_verified = False
            try:
                is_verified = await container.user_manager.is_verified(user_id)
            except Exception:
                is_verified = False

            # Treat globally verified users as trusted enough to enter during raid mode,
            # but still require the group's join verification to speak.
            if not is_verified:
                try:
                    bot_me = await event.bot.get_me()
                    await event.bot.ban_chat_member(chat_id=group_id, user_id=user_id)
                    await event.bot.unban_chat_member(chat_id=group_id, user_id=user_id)
                    await container.admin_service.log_custom_action(
                        event.bot,
                        group_id,
                        actor_id=int(bot_me.id),
                        target_id=int(user_id),
                        action="raid_kick",
                        reason="Raid mode active: blocked new join",
                    )
                except Exception:
                    pass
                return

        # Join-quality heuristic: optionally block users without a Telegram @username (unless whitelisted/verified).
        if bool(getattr(group, "block_no_username", False)) and not (username or "").strip():
            try:
                if await container.whitelist_service.is_whitelisted(group_id, user_id):
                    await _send_welcome(event.bot, group_id, new_member)
                    return
            except Exception:
                pass

            is_verified = False
            try:
                is_verified = await container.user_manager.is_verified(user_id)
            except Exception:
                is_verified = False

            # Allow globally verified users to proceed even without a username,
            # but still require the group's join verification to speak.
            if not is_verified:
                try:
                    bot_me = await event.bot.get_me()
                    await event.bot.ban_chat_member(chat_id=group_id, user_id=user_id)
                    await event.bot.unban_chat_member(chat_id=group_id, user_id=user_id)
                    await container.admin_service.log_custom_action(
                        event.bot,
                        group_id,
                        actor_id=int(bot_me.id),
                        target_id=int(user_id),
                        action="block_no_username",
                        reason="Blocked new join: user has no @username (join-quality rule)",
                    )
                except Exception:
                    pass
                return

        if not group.verification_enabled:
            logger.info(f"Verification disabled for group {group_id}; allowing user {user_id}")
            await _send_welcome(event.bot, group_id, new_member)
            return

        # Whitelist bypass (per-group)
        try:
            if await container.whitelist_service.is_whitelisted(group_id, user_id):
                logger.info(f"User {user_id} is whitelisted in group {group_id}; allowing access")
                await _send_welcome(event.bot, group_id, new_member)
                return
        except Exception:
            pass
        
        # NOTE: We do NOT skip the DM interaction even if user is verified globally
        # The user must still click the verification link so the bot can:
        # 1. Collect user data for this specific group
        # 2. Show group-specific rules if enabled
        # 3. Track that they've interacted with the bot for this group
        # The 7-day skip only applies to the Mercle SDK step itself (handled in verification panel)
        
        try:
            # Verify bot has permissions before restricting
            if not await is_bot_admin(event.bot, group_id):
                await event.bot.send_message(chat_id=group_id, text="I need to be admin. Run <code>/checkperms</code>.", parse_mode="HTML")
                return
            bot_info = await event.bot.get_me()
            restrict_ok = await can_restrict_members(event.bot, group_id, bot_info.id)
            if not restrict_ok:
                await event.bot.send_message(chat_id=group_id, text="I need Restrict members. Run <code>/checkperms</code>.", parse_mode="HTML")
                return

            # Create pending record first
            # Check if there's an existing VALID pending verification (not expired, has recent message)
            existing = await container.pending_verification_service.get_active_for_user(group_id, user_id)
            should_create_new = True
            
            if existing and existing.expires_at > datetime.utcnow():
                # Existing pending verification is still valid (not expired)
                # Check if it was created very recently (within last 30 seconds) - likely a duplicate event
                time_since_created = (datetime.utcnow() - existing.created_at).total_seconds() if hasattr(existing, 'created_at') else 999
                if time_since_created < 30 and existing.prompt_message_id:
                    # Very recent - reuse it
                    pending = existing
                    should_create_new = False
                    logger.info(f"Reusing recent pending verification {existing.id} for user {user_id} in group {group_id}")
                else:
                    # Expired or old - create new one
                    logger.info(f"Existing pending verification is old or expired for user {user_id}, creating new one")
            
            if should_create_new:
                # Create new pending verification
                timeout_seconds = int(group.verification_timeout or container.config.verification_timeout)
                pending = await container.pending_verification_service.create_pending(
                    group_id=group_id,
                    telegram_id=user_id,
                    expires_at=datetime.utcnow() + timedelta(seconds=timeout_seconds),
                )
                logger.info(f"Created new pending verification {pending.id} for user {user_id} in group {group_id}")

            # Restrict user (even if already restricted, ensure permissions are correct)
            await event.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
            )

            # Always send verification message (unless we just reused a very recent one)
            if should_create_new:
                # Create expiring deep link token bound to (group_id, user_id)
                bot_username = bot_info.username or ""
                minutes = max(1, int((pending.expires_at - datetime.utcnow()).total_seconds() // 60))
                token = await container.token_service.create_verification_token(
                    pending_id=int(pending.id),
                    group_id=group_id,
                    telegram_id=user_id,
                    expires_at=pending.expires_at,
                )
                deep_link = f"https://t.me/{bot_username}?start=ver_{token}" if bot_username else ""

                prompt_text = f"👋 {new_member.mention_html()} — verify in DM to chat.\n⏱ Time left: {minutes} min"
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Verify in DM", url=deep_link)] if deep_link else [],
                        # Manual Approve/Reject removed - Mercle SDK is single source of truth
                    ]
                )
                keyboard.inline_keyboard = [row for row in keyboard.inline_keyboard if row]
                sent = await event.bot.send_message(chat_id=group_id, text=prompt_text, parse_mode="HTML", reply_markup=keyboard)
                await container.pending_verification_service.set_prompt_message_id(int(pending.id), sent.message_id)
                logger.info(f"Sent verification message for user {user_id} in group {group_id}")
            
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
    
    # REMOVED: Manual verification approve/reject callbacks
    # Mercle SDK is the single source of truth for verification
    # The pv: callback handler has been disabled

    # Handle NEW_CHAT_MEMBERS message events (for users who rejoin while restricted)
    @router.message(F.new_chat_members)
    async def on_new_chat_members_message(message):
        """
        Handle NEW_CHAT_MEMBERS message event.
        This triggers when users join via invite link or are added, even if already restricted.
        """
        try:
            logger.info(f"NEW_CHAT_MEMBERS: chat={message.chat.id} ({message.chat.title}), members={len(message.new_chat_members) if message.new_chat_members else 0}")
            
            if not message.new_chat_members:
                logger.warning("🔥 No new_chat_members in message, returning")
                return
        except Exception as e:
            logger.error(f"❌ Error in NEW_CHAT_MEMBERS handler initialization: {e}", exc_info=True)
            return
        
        for new_member in message.new_chat_members:
            try:
                if new_member.is_bot:
                    logger.info(f"Bot @{new_member.username} added to group {message.chat.id}")
                    continue
                
                user_id = new_member.id
                username = new_member.username
                group_id = message.chat.id
                group_name = message.chat.title or "this group"
                
                logger.info(f"👤 New member (message event): {user_id} (@{username}) joined group {group_id} ({group_name})")
                
                # Register group and touch user
                await container.group_service.register_group(group_id, group_name)
                await container.pending_verification_service.touch_group_user(
                    group_id,
                    user_id,
                    username=username,
                    first_name=new_member.first_name,
                    last_name=new_member.last_name,
                    source="join",
                    increment_join=True,
                )
                
                # Load group settings
                group = await container.group_service.get_or_create_group(group_id)
                
                # Check if verification is enabled
                if not group.verification_enabled:
                    logger.info(f"Verification disabled for group {group_id}; allowing user {user_id}")
                    await _send_welcome(message.bot, group_id, new_member)
                    continue
                
                # Check whitelist
                try:
                    if await container.whitelist_service.is_whitelisted(group_id, user_id):
                        logger.info(f"User {user_id} is whitelisted in group {group_id}; allowing access")
                        await _send_welcome(message.bot, group_id, new_member)
                        continue
                except Exception:
                    pass
                
                # Start verification flow
                try:
                    # Verify bot has permissions
                    if not await is_bot_admin(message.bot, group_id):
                        await message.bot.send_message(chat_id=group_id, text="I need to be admin. Run <code>/checkperms</code>.", parse_mode="HTML")
                        continue
                    
                    bot_info = await message.bot.get_me()
                    restrict_ok = await can_restrict_members(message.bot, group_id, bot_info.id)
                    if not restrict_ok:
                        await message.bot.send_message(chat_id=group_id, text="I need Restrict members. Run <code>/checkperms</code>.", parse_mode="HTML")
                        continue
                    
                    # Check for existing valid pending verification
                    existing = await container.pending_verification_service.get_active_for_user(group_id, user_id)
                    should_create_new = True
                    
                    if existing and existing.expires_at > datetime.utcnow():
                        # Check if created very recently (< 30 seconds)
                        time_since_created = (datetime.utcnow() - existing.created_at).total_seconds() if hasattr(existing, 'created_at') else 999
                        if time_since_created < 30 and existing.prompt_message_id:
                            pending = existing
                            should_create_new = False
                            logger.info(f"Reusing recent pending verification {existing.id} for user {user_id}")
                        else:
                            logger.info(f"Existing pending verification is old for user {user_id}, creating new one")
                    
                    if should_create_new:
                        timeout_seconds = int(group.verification_timeout or container.config.verification_timeout)
                        pending = await container.pending_verification_service.create_pending(
                            group_id=group_id,
                            telegram_id=user_id,
                            expires_at=datetime.utcnow() + timedelta(seconds=timeout_seconds),
                        )
                        logger.info(f"Created new pending verification {pending.id} for user {user_id}")
                    
                    # Restrict user
                    await message.bot.restrict_chat_member(
                        chat_id=group_id,
                        user_id=user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                    )
                    
                    # Send verification message
                    if should_create_new:
                        bot_username = bot_info.username or ""
                        minutes = max(1, int((pending.expires_at - datetime.utcnow()).total_seconds() // 60))
                        token = await container.token_service.create_verification_token(
                            pending_id=int(pending.id),
                            group_id=group_id,
                            telegram_id=user_id,
                            expires_at=pending.expires_at,
                        )
                        deep_link = f"https://t.me/{bot_username}?start=ver_{token}" if bot_username else ""
                        
                        prompt_text = f"👋 {new_member.mention_html()} — verify in DM to chat.\n⏱ Time left: {minutes} min"
                        keyboard = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [InlineKeyboardButton(text="✅ Verify in DM", url=deep_link)] if deep_link else [],
                            ]
                        )
                        keyboard.inline_keyboard = [row for row in keyboard.inline_keyboard if row]
                        sent = await message.bot.send_message(chat_id=group_id, text=prompt_text, parse_mode="HTML", reply_markup=keyboard)
                        await container.pending_verification_service.set_prompt_message_id(int(pending.id), sent.message_id)
                        logger.info(f"Sent verification message for user {user_id} in group {group_id}")
                        
                except Exception as e:
                    logger.error(f"❌ Error in verification flow for user {user_id}: {e}", exc_info=True)
                    try:
                        await message.bot.send_message(
                            chat_id=group_id,
                            text=f"⚠️ Error starting verification for @{username}. Please try `/verify` in a private message with me.",
                            parse_mode="Markdown"
                        )
                    except Exception as notify_error:
                        logger.error(f"❌ Failed to send error notification: {notify_error}")
                        
            except Exception as e:
                logger.error(f"❌ Error processing new member {user_id}: {e}", exc_info=True)

    return router


def create_leave_handlers(container: ServiceContainer) -> Router:
    """
    Separate router for member leave events (goodbye messages).
    """
    router = Router()

    @router.chat_member(ChatMemberUpdatedFilter(member_status_changed=(MEMBER | RESTRICTED) >> (LEFT | KICKED)))
    async def on_member_left(event: ChatMemberUpdated):
        user = event.old_chat_member.user
        if user.is_bot:
            return
        group_id = event.chat.id

        # If the user leaves while pending verification, cancel the pending and remove the prompt (best-effort).
        try:
            pending = await container.pending_verification_service.get_active_for_user(int(group_id), int(user.id))
            if pending:
                bot_me = await event.bot.get_me()
                await container.pending_verification_service.decide(int(pending.id), status="cancelled", decided_by=int(bot_me.id))
                await container.pending_verification_service.delete_group_prompt(event.bot, pending)
        except Exception:
            pass

        try:
            goodbye = await container.welcome_service.get_goodbye(group_id)
            if not goodbye:
                return
            enabled, template = goodbye
            if not enabled or not template:
                return
            group = await container.group_service.get_or_create_group(group_id)
            group_name = group.group_name or "this group"
            try:
                member_count = await event.bot.get_chat_member_count(group_id)
            except Exception:
                member_count = 0
            name = user.full_name or user.first_name or "there"
            mention = user.mention_html()
            text = container.welcome_service.format_message(template, name, mention, group_name, int(member_count or 0))
            await event.bot.send_message(chat_id=group_id, text=text, parse_mode="HTML")
        except Exception:
            return

    return router


def create_admin_join_handlers(container: ServiceContainer) -> Router:
    """
    Separate router for bot-added-to-group / admin setup message.
    """
    router = Router()
    
    # Important: Telegram sends updates about the bot itself as `my_chat_member`,
    # not `chat_member`. This is what makes the setup card appear when the bot is added.
    @router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=(LEFT | KICKED) >> (MEMBER | ADMINISTRATOR)))
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
        
        await _send_or_update_setup_card(event.bot, container, group_id, group_name)
    
    @router.callback_query(lambda c: c.data and c.data.startswith("setup:"))
    async def setup_card_callbacks(callback: CallbackQuery):
        # setup:recheck:<group_id> | setup:help
        parts = callback.data.split(":")
        if len(parts) < 2:
            await callback.answer("Not allowed", show_alert=True)
            return
        action = parts[1]

        if action == "help":
            await callback.answer()
            await callback.message.answer("Promote the bot to admin and enable Restrict + Delete, then use the Mini App.", parse_mode="HTML")
            return

        if action == "recheck":
            if len(parts) != 3:
                await callback.answer("Not allowed", show_alert=True)
                return
            try:
                group_id = int(parts[2])
            except ValueError:
                await callback.answer("Not allowed", show_alert=True)
                return

            # Only group admins can re-check
            if not await is_user_admin(callback.bot, group_id, callback.from_user.id):
                await callback.answer("Not allowed", show_alert=True)
                return

            group = await container.group_service.get_or_create_group(group_id)
            await callback.answer()
            await _send_or_update_setup_card(callback.bot, container, group_id, group.group_name or str(group_id), message_id=callback.message.message_id)
            return

        await callback.answer("Not allowed", show_alert=True)

    return router


async def _send_or_update_setup_card(bot, container: ServiceContainer, group_id: int, group_name: str, message_id: int | None = None):
    bot_info = await bot.get_me()
    bot_member = await bot.get_chat_member(group_id, bot_info.id)
    restrict_ok = bool(getattr(bot_member, "can_restrict_members", False))
    delete_ok = bool(getattr(bot_member, "can_delete_messages", False))
    pin_ok = bool(getattr(bot_member, "can_pin_messages", False))
    status_line = f"Restrict: {'✅' if restrict_ok else '❌'}  Delete: {'✅' if delete_ok else '❌'}  Pin: {'✅' if pin_ok else '◻️'} (opt)"

    if restrict_ok and delete_ok:
        text = "✅ Ready. Use /actions to moderate. Use the Mini App to configure."
        auto_delete_after = 600
    else:
        text = (
            "<b>Setup</b>\n"
            "1) Promote me to admin\n"
            "2) Enable: Restrict, Delete\n"
            "3) Use the Mini App to configure\n\n"
            f"{status_line}"
        )
        auto_delete_after = None

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Re-check", callback_data=f"setup:recheck:{group_id}")],
            [InlineKeyboardButton(text="Help", callback_data="setup:help")],
        ]
    )

    if not message_id:
        async with db.session() as session:
            result = await session.execute(select(GroupWizardState).where(GroupWizardState.group_id == group_id))
            state = result.scalar_one_or_none()
            if state and state.setup_card_message_id:
                message_id = int(state.setup_card_message_id)

    if message_id:
        try:
            await bot.edit_message_text(chat_id=group_id, message_id=message_id, text=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            message_id = None

    if not message_id:
        sent = await bot.send_message(chat_id=group_id, text=text, parse_mode="HTML", reply_markup=kb)
        message_id = sent.message_id

    # Persist message id for later edits
    async with db.session() as session:
        result = await session.execute(select(GroupWizardState).where(GroupWizardState.group_id == group_id))
        state = result.scalar_one_or_none()
        if not state:
            state = GroupWizardState(group_id=group_id, wizard_completed=False, wizard_step=1)
            session.add(state)
        state.setup_card_message_id = message_id

    if auto_delete_after:
        async def _del():
            await asyncio.sleep(auto_delete_after)
            try:
                await bot.delete_message(chat_id=group_id, message_id=message_id)
            except Exception:
                try:
                    await bot.edit_message_reply_markup(chat_id=group_id, message_id=message_id, reply_markup=None)
                except Exception:
                    pass
                try:
                    await bot.edit_message_text(chat_id=group_id, message_id=message_id, text="✅ Resolved.", parse_mode="HTML")
                except Exception:
                    pass

        asyncio.create_task(_del())
