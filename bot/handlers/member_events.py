"""Member event handlers for group management - simplified."""
import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import Router
from aiogram.types import ChatMemberUpdated, CallbackQuery
from aiogram.filters import ChatMemberUpdatedFilter, MEMBER, RESTRICTED, LEFT, KICKED

from bot.container import ServiceContainer
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import ChatPermissions

from bot.utils.permissions import is_user_admin, has_role_permission, is_bot_admin, can_restrict_members, can_delete_messages, can_pin_messages
from database.db import db
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
        await container.pending_verification_service.touch_group_user(group_id, user_id)
        
        # Load group settings
        group = await container.group_service.get_or_create_group(group_id)
        if not group.verification_enabled:
            logger.info(f"Verification disabled for group {group_id}; allowing user {user_id}")
            return
        
        # Check if already verified globally
        is_verified = await container.user_manager.is_verified(user_id)
        
        if is_verified:
            logger.info(f"✅ User {user_id} is already verified globally, allowing access")
            await container.pending_verification_service.mark_group_user_verified(group_id, user_id)
            return
        
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

            # Create pending record first (idempotency: if one exists, reuse it)
            existing = await container.pending_verification_service.get_active_for_user(group_id, user_id)
            if existing:
                pending = existing
            else:
                timeout_seconds = int(group.verification_timeout or container.config.verification_timeout)
                pending = await container.pending_verification_service.create_pending(
                    group_id=group_id,
                    telegram_id=user_id,
                    expires_at=datetime.utcnow() + timedelta(seconds=timeout_seconds),
                )

            # Restrict user
            await event.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
            )

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

            prompt_text = f"{new_member.mention_html()} verify to chat.\nTime: {minutes} min"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Verify in DM", url=deep_link)] if deep_link else [],
                    [
                        InlineKeyboardButton(text="Approve", callback_data=f"pv:{pending.id}:approve"),
                        InlineKeyboardButton(text="Reject", callback_data=f"pv:{pending.id}:reject"),
                    ],
                ]
            )
            keyboard.inline_keyboard = [row for row in keyboard.inline_keyboard if row]
            sent = await event.bot.send_message(chat_id=group_id, text=prompt_text, parse_mode="HTML", reply_markup=keyboard)
            await container.pending_verification_service.set_prompt_message_id(int(pending.id), sent.message_id)
            
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
    
    @router.callback_query(lambda c: c.data and c.data.startswith("pv:"))
    async def pending_verification_callbacks(callback: CallbackQuery):
        # pv:<pending_id>:approve|reject
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Not allowed", show_alert=True)
            return
        _, pending_str, action = parts
        try:
            pending_id = int(pending_str)
        except ValueError:
            await callback.answer("Not allowed", show_alert=True)
            return

        pending = await container.pending_verification_service.get_pending(pending_id)
        if not pending or pending.status != "pending":
            await callback.answer("Link expired.", show_alert=True)
            return

        group_id = int(pending.group_id)
        actor_id = callback.from_user.id

        # Permission check: telegram admin OR custom role that can_verify
        if not await is_user_admin(callback.bot, group_id, actor_id):
            if not await has_role_permission(group_id, actor_id, "verify"):
                await callback.answer("Not allowed", show_alert=True)
                return

        # Bot needs restrict to approve/reject (kick)
        if not await is_bot_admin(callback.bot, group_id):
            await callback.answer("Bot not admin.", show_alert=True)
            return

        if action == "approve":
            try:
                await callback.bot.restrict_chat_member(
                    chat_id=group_id,
                    user_id=int(pending.telegram_id),
                    permissions=ChatPermissions(
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_polls=True,
                        can_send_other_messages=True,
                        can_add_web_page_previews=True,
                        can_change_info=False,
                        can_invite_users=True,
                        can_pin_messages=False,
                    ),
                )
            except Exception:
                await callback.answer("Failed.", show_alert=True)
                return
            await container.pending_verification_service.decide(pending_id, status="approved", decided_by=actor_id)
            await container.pending_verification_service.delete_group_prompt(callback.bot, pending)
            await callback.answer("Approved")
            return

        if action == "reject":
            try:
                await callback.bot.ban_chat_member(chat_id=group_id, user_id=int(pending.telegram_id))
                await callback.bot.unban_chat_member(chat_id=group_id, user_id=int(pending.telegram_id))
            except Exception:
                await callback.answer("Failed.", show_alert=True)
                return
            await container.pending_verification_service.decide(pending_id, status="rejected", decided_by=actor_id)
            await container.pending_verification_service.edit_or_delete_group_prompt(callback.bot, pending, "🚫 Rejected")
            await callback.answer("Rejected")
            return

        await callback.answer("Not allowed", show_alert=True)

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
            await callback.message.answer("Promote the bot to admin and enable Restrict + Delete, then run /menu.", parse_mode="HTML")
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
        text = "✅ Ready. Use /actions to moderate. Use /menu to configure."
        auto_delete_after = 600
    else:
        text = (
            "<b>Setup</b>\n"
            "1) Promote me to admin\n"
            "2) Enable: Restrict, Delete\n"
            "3) Run <code>/menu</code>\n\n"
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
    from database.models import GroupWizardState

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
                pass

        asyncio.create_task(_del())
