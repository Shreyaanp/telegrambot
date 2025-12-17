"""Join request handlers - optional pre-join verification gate.

This only works if the group is configured by admins to require join requests
(Telegram setting: "Approve new members"). Bots cannot enable that setting.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.types import ChatJoinRequest, InlineKeyboardMarkup, InlineKeyboardButton

from bot.container import ServiceContainer

logger = logging.getLogger(__name__)

JOIN_REQUEST_DM_WINDOW_SECONDS = 5 * 60


def create_join_request_handlers(container: ServiceContainer) -> Router:
    router = Router()

    @router.chat_join_request()
    async def on_join_request(req: ChatJoinRequest):
        group_id = req.chat.id
        group_title = req.chat.title or str(group_id)
        user = req.from_user
        user_id = user.id
        user_chat_id = getattr(req, "user_chat_id", None)
        # ChatJoinRequest.date is a unix timestamp (seconds) in the Bot API.
        try:
            join_request_at = datetime.utcfromtimestamp(int(getattr(req, "date")))
        except Exception:
            join_request_at = datetime.utcnow()

        await container.group_service.register_group(group_id, group_title)

        group = await container.group_service.get_or_create_group(group_id)
        if not getattr(group, "join_gate_enabled", False):
            return

        # Keep behavior predictable: if verification is off, just approve.
        if not getattr(group, "verification_enabled", True):
            try:
                await req.bot.approve_chat_join_request(chat_id=group_id, user_id=user_id)
            except Exception:
                pass
            return

        # Record that we saw this user for this group (even before they join).
        await container.pending_verification_service.touch_group_user(
            group_id,
            user_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            source="join_request",
            increment_join=False,
        )

        # Whitelist / already verified -> approve immediately.
        try:
            if await container.whitelist_service.is_whitelisted(group_id, user_id):
                await req.bot.approve_chat_join_request(chat_id=group_id, user_id=user_id)
                return
        except Exception:
            pass

        try:
            if await container.user_manager.is_verified(user_id):
                await req.bot.approve_chat_join_request(chat_id=group_id, user_id=user_id)
                return
        except Exception:
            pass

        timeout_seconds = int(group.verification_timeout or container.config.verification_timeout)
        expires_at = datetime.utcnow() + timedelta(seconds=timeout_seconds)

        existing = await container.pending_verification_service.get_active_for_user(group_id, user_id, kind="join_request")
        pending = existing
        if not pending:
            pending = await container.pending_verification_service.create_pending(
                group_id=group_id,
                telegram_id=user_id,
                expires_at=expires_at,
                kind="join_request",
                user_chat_id=int(user_chat_id) if user_chat_id is not None else None,
                join_request_at=join_request_at,
            )

        bot_info = await req.bot.get_me()
        token = await container.token_service.create_verification_token(
            pending_id=int(pending.id),
            group_id=group_id,
            telegram_id=user_id,
            expires_at=pending.expires_at,
        )
        deep_link = f"https://t.me/{bot_info.username}?start=ver_{token}" if bot_info.username else ""
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Verify to Join", url=deep_link)]])

        # DM the join-request user. Prefer `user_chat_id` (works even if they never started the bot, within a short window).
        try:
            if user_chat_id is None:
                raise RuntimeError("user_chat_id is missing; cannot DM join-request user reliably")

            age = (datetime.utcnow() - join_request_at).total_seconds()
            if age > JOIN_REQUEST_DM_WINDOW_SECONDS:
                raise RuntimeError(f"join-request DM window missed (age={int(age)}s)")

            dm_chat_id = int(user_chat_id)
            msg = await req.bot.send_message(
                chat_id=dm_chat_id,
                text=(
                    f"<b>Verification required</b>\n"
                    f"Group: {group_title}\n\n"
                    f"Tap below to verify. After approval, I will approve your join request."
                ),
                parse_mode="HTML",
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            await container.pending_verification_service.set_dm_message_id(int(pending.id), msg.message_id)
        except Exception as e:
            logger.info(f"Failed to DM join-request user {user_id} for group {group_id}: {e}")
            # If we can't message them to verify, we can't complete this flow; decline request.
            try:
                await req.bot.decline_chat_join_request(chat_id=group_id, user_id=user_id)
            except Exception:
                pass
            try:
                bot_me = await req.bot.get_me()
                await container.pending_verification_service.decide(int(pending.id), status="rejected", decided_by=bot_me.id)
            except Exception:
                pass

    return router
