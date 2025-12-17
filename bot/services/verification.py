"""Verification service - simplified and user-friendly."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, ChatPermissions

from bot.config import Config
from bot.services.mercle_sdk import MercleSDK
from bot.services.user_manager import UserManager
from bot.services.group_service import GroupService
from bot.services.metrics_service import MetricsService
from bot.services.pending_verification_service import PendingVerificationService
from bot.utils.qr_generator import generate_qr_code, decode_base64_qr
from bot.utils.messages import (
    verification_prompt_message,
    verification_success_message,
    verification_timeout_message,
    verification_failed_message,
    verification_error_message,
)

logger = logging.getLogger(__name__)


class VerificationService:
    """
    Handles verification flow with Mercle SDK.
    
    Simplified flow:
    1. User triggers verification (auto-join or /verify command)
    2. Create Mercle session and send QR + buttons
    3. Poll for verification status
    4. Handle success/failure/timeout
    """
    
    def __init__(
        self,
        config: Config,
        mercle_sdk: MercleSDK,
        user_manager: UserManager,
        group_service: GroupService,
        metrics_service: MetricsService,
        pending_verification_service: PendingVerificationService | None = None,
    ):
        """Initialize verification service."""
        self.config = config
        self.mercle_sdk = mercle_sdk
        self.user_manager = user_manager
        self.group_service = group_service
        self.metrics = metrics_service
        self.pending = pending_verification_service
        self.active_verifications = {}  # session_id -> asyncio.Task
    
    async def start_verification(
        self,
        bot: Bot,
        telegram_id: int,
        chat_id: int,
        username: Optional[str] = None,
        group_id: Optional[int] = None
    ) -> bool:
        """
        Start verification flow for a user.
        
        Args:
            bot: Bot instance
            telegram_id: User's Telegram ID
            chat_id: Where to send verification message (user DM or group)
            username: User's Telegram username
            group_id: Group ID if verification is for group join
            
        Returns:
            True if verification started successfully, False otherwise
        """
        try:
            logger.info(f"Starting verification for user {telegram_id} ({username})")
            
            # Determine per-group settings
            timeout_seconds = self.config.verification_timeout
            action_on_timeout = self.config.action_on_timeout
            if group_id:
                group = await self.group_service.get_or_create_group(group_id)
                timeout_seconds = group.verification_timeout or timeout_seconds
                action_on_timeout = "kick" if group.kick_unverified else "mute"
            
            # Create Mercle SDK session
            metadata = {
                "telegram_user_id": telegram_id,
                "telegram_username": username or "unknown",
                "timestamp": datetime.utcnow().isoformat(),
            }
            if group_id:
                metadata["group_id"] = group_id
            
            sdk_response = await self.mercle_sdk.create_session(metadata=metadata)
            session_id = sdk_response["session_id"]
            base64_qr = sdk_response.get("base64_qr", "")
            qr_data = sdk_response.get("qr_data", "")
            
            logger.info(f"Created Mercle session: {session_id}")
            
            # Save session to database
            expires_at = datetime.utcnow() + timedelta(seconds=timeout_seconds)
            await self.user_manager.create_session(
                session_id=session_id,
                telegram_id=telegram_id,
                chat_id=chat_id,
                expires_at=expires_at,
                telegram_username=username,
                group_id=group_id
            )
            
            # Generate QR code image
            qr_json = decode_base64_qr(base64_qr) if base64_qr else qr_data
            qr_image = generate_qr_code(qr_json) if qr_json else None
            
            # Create universal link for mobile users
            import urllib.parse
            universal_link = (
                f"https://telegram.mercle.ai/verify"
                f"?session_id={session_id}"
                f"&app_name={urllib.parse.quote('Telegram Verification Bot')}"
                f"&app_domain={urllib.parse.quote('https://telegram.mercle.ai')}"
                f"&base64_qr={urllib.parse.quote(base64_qr)}"
            )
            
            # Build inline keyboard with clear CTAs
            keyboard = [
                [
                    InlineKeyboardButton(
                        text="🚀 Verify Now (Tap Here!)",
                        url=universal_link
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📥 Get Mercle App (iOS)",
                        url=self.config.mercle_ios_url
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📥 Get Mercle App (Android)",
                        url=self.config.mercle_android_url
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            
            # Send verification message
            message_text = verification_prompt_message(timeout_seconds)
            
            sent_message = None
            if qr_image:
                qr_file = BufferedInputFile(qr_image.read(), filename="qr_code.png")
                sent_message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=qr_file,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                sent_message = await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            # Store message ID for later deletion
            if sent_message:
                await self.user_manager.store_message_ids(session_id, [sent_message.message_id])
            
            # Start polling task in background
            task = asyncio.create_task(
                self._poll_verification(
                    bot,
                    session_id,
                    telegram_id,
                    chat_id,
                    group_id,
                    timeout_seconds,
                    action_on_timeout
                )
            )
            self.active_verifications[session_id] = task
            
            logger.info(f"✅ Verification started for user {telegram_id}")
            await self.metrics.incr_verification("started")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start verification: {e}", exc_info=True)
            
            # Send error message to user
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=verification_error_message(),
                    parse_mode="Markdown"
                )
            except:
                pass
            
            return False

    async def start_verification_panel(
        self,
        *,
        bot: Bot,
        telegram_id: int,
        chat_id: int,
        username: Optional[str] = None,
        group_id: Optional[int] = None,
        pending_id: Optional[int] = None,
        message_id: Optional[int] = None,
        pending_kind: Optional[str] = None,
    ) -> bool:
        """
        Start Mercle verification in a single message (edit-in-place, no extra success/fail messages).
        Used for the join flow DM deep link.
        """
        try:
            timeout_seconds = self.config.verification_timeout
            action_on_timeout = self.config.action_on_timeout
            group_name = None
            if group_id:
                group = await self.group_service.get_or_create_group(group_id)
                group_name = group.group_name
                timeout_seconds = group.verification_timeout or timeout_seconds
                action_on_timeout = "kick" if group.kick_unverified else "mute"

            metadata = {
                "telegram_user_id": telegram_id,
                "telegram_username": username or "unknown",
                "timestamp": datetime.utcnow().isoformat(),
            }
            if group_id:
                metadata["group_id"] = group_id
            if pending_id:
                metadata["pending_id"] = pending_id

            sdk_response = await self.mercle_sdk.create_session(metadata=metadata)
            session_id = sdk_response["session_id"]
            base64_qr = sdk_response.get("base64_qr", "")

            expires_at = datetime.utcnow() + timedelta(seconds=int(timeout_seconds))
            await self.user_manager.create_session(
                session_id=session_id,
                telegram_id=telegram_id,
                chat_id=chat_id,
                expires_at=expires_at,
                telegram_username=username,
                group_id=group_id,
            )

            if pending_id and self.pending:
                await self.pending.attach_session(pending_id, session_id)

            import urllib.parse

            universal_link = (
                f"https://telegram.mercle.ai/verify"
                f"?session_id={session_id}"
                f"&app_name={urllib.parse.quote('MercleMerci')}"
                f"&app_domain={urllib.parse.quote('https://telegram.mercle.ai')}"
                f"&base64_qr={urllib.parse.quote(base64_qr)}"
            )

            header = "<b>Verification</b>"
            if group_id:
                header = f"<b>Verification</b>\nGroup: {group_name or group_id}"
            text = f"{header}\n\nOpen Mercle to verify."
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Open Mercle", url=universal_link)]]
            )

            if message_id:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
                await self.user_manager.store_message_ids(session_id, [message_id])
                panel_message_id = message_id
            else:
                sent = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
                await self.user_manager.store_message_ids(session_id, [sent.message_id])
                panel_message_id = sent.message_id

            task = asyncio.create_task(
                self._poll_verification(
                    bot,
                    session_id,
                    telegram_id,
                    chat_id,
                    group_id,
                    int(timeout_seconds),
                    action_on_timeout,
                    pending_id=pending_id,
                    panel_message_id=panel_message_id,
                    pending_kind=pending_kind,
                )
            )
            self.active_verifications[session_id] = task
            await self.metrics.incr_verification("started")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to start verification panel: {e}", exc_info=True)
            return False
    
    async def _poll_verification(
        self,
        bot: Bot,
        session_id: str,
        telegram_id: int,
        chat_id: int,
        group_id: Optional[int],
        timeout_seconds: int,
        action_on_timeout: str,
        pending_id: Optional[int] = None,
        panel_message_id: Optional[int] = None,
        pending_kind: Optional[str] = None,
    ):
        """
        Poll Mercle SDK for verification status.
        
        This runs in the background and checks every 3 seconds.
        """
        timeout = timeout_seconds
        poll_interval = 3  # Check every 3 seconds
        max_polls = timeout // poll_interval
        
        try:
            logger.info(f"Polling verification for session {session_id}")
            
            for i in range(max_polls):
                await asyncio.sleep(poll_interval)
                
                # Check session status from Mercle
                status_response = await self.mercle_sdk.check_status(session_id)
                status = status_response.get("status")
                
                logger.debug(f"Session {session_id} status: {status} (poll {i+1}/{max_polls})")
                
                if status == "approved":
                    # Success! User verified
                    mercle_user_id = status_response.get("localized_user_id")
                    await self._handle_success(
                        bot,
                        session_id,
                        telegram_id,
                        chat_id,
                        mercle_user_id,
                        group_id,
                        send_followup=(panel_message_id is None),
                        panel_message_id=panel_message_id,
                        pending_kind=pending_kind,
                    )
                    if pending_id and self.pending:
                        await self.pending.decide(pending_id, status="approved", decided_by=telegram_id)
                        pending = await self.pending.get_pending(pending_id)
                        if pending:
                            await self.pending.delete_group_prompt(bot, pending)
                        if group_id:
                            await self.pending.mark_group_user_verified(int(group_id), telegram_id, session_id)
                        try:
                            kind = getattr(pending, "kind", None) if pending else None
                            if (pending_kind == "join_request" or kind == "join_request") and group_id:
                                await bot.approve_chat_join_request(chat_id=int(group_id), user_id=int(telegram_id))
                        except Exception:
                            pass
                    await self.metrics.incr_verification("approved")
                    return
                
                elif status in ["rejected", "expired"]:
                    # Verification failed
                    await self._handle_failure(
                        bot,
                        session_id,
                        chat_id,
                        group_id,
                        telegram_id,
                        action_on_timeout,
                        send_followup=(panel_message_id is None),
                        panel_message_id=panel_message_id,
                        pending_kind=pending_kind,
                    )
                    if pending_id and self.pending:
                        await self.pending.decide(pending_id, status="rejected", decided_by=telegram_id)
                        pending = await self.pending.get_pending(pending_id)
                        if pending:
                            await self.pending.edit_or_delete_group_prompt(bot, pending, "🚫 Rejected")
                        try:
                            kind = getattr(pending, "kind", None) if pending else None
                            if (pending_kind == "join_request" or kind == "join_request") and group_id:
                                await bot.decline_chat_join_request(chat_id=int(group_id), user_id=int(telegram_id))
                        except Exception:
                            pass
                    await self.metrics.incr_verification(status)
                    return
            
            # Timeout reached without completion
            logger.warning(f"Verification timeout for session {session_id}")
            await self._handle_timeout(
                bot,
                session_id,
                chat_id,
                group_id,
                telegram_id,
                action_on_timeout,
                send_followup=(panel_message_id is None),
                panel_message_id=panel_message_id,
                pending_kind=pending_kind,
            )
            if pending_id and self.pending:
                await self.pending.decide(pending_id, status="timed_out", decided_by=telegram_id)
                pending = await self.pending.get_pending(pending_id)
                if pending:
                    await self.pending.edit_or_delete_group_prompt(bot, pending, "⏱ Timed out")
                try:
                    kind = getattr(pending, "kind", None) if pending else None
                    if (pending_kind == "join_request" or kind == "join_request") and group_id:
                        await bot.decline_chat_join_request(chat_id=int(group_id), user_id=int(telegram_id))
                except Exception:
                    pass
            
        except asyncio.CancelledError:
            logger.info(f"Polling cancelled for session {session_id}")
            raise
        except Exception as e:
            logger.error(f"Error polling verification: {e}", exc_info=True)
        finally:
            # Clean up
            if session_id in self.active_verifications:
                del self.active_verifications[session_id]
    
    async def _handle_success(
        self,
        bot: Bot,
        session_id: str,
        telegram_id: int,
        chat_id: int,
        mercle_user_id: str,
        group_id: Optional[int] = None,
        *,
        send_followup: bool = True,
        panel_message_id: Optional[int] = None,
        pending_kind: Optional[str] = None,
    ):
        """Handle successful verification."""
        try:
            logger.info(f"✅ Verification successful for user {telegram_id}")
            
            # Get session details
            session_obj = await self.user_manager.get_session(session_id)
            username = session_obj.telegram_username if session_obj else None
            
            # Delete verification messages if configured (skip for panel flows that edit in place)
            if send_followup and self.config.auto_delete_verification_messages and session_obj and session_obj.message_ids:
                await self._delete_messages(bot, chat_id, session_obj.message_ids)
            
            # Create/update user in database
            await self.user_manager.create_user(
                telegram_id=telegram_id,
                mercle_user_id=mercle_user_id,
                username=username
            )
            
            # Update session status
            await self.user_manager.update_session_status(session_id, "approved")
            
            # If this was for a group, unmute the user (skip for join-request gating; user isn't a member yet).
            if group_id and pending_kind != "join_request":
                try:
                    await bot.restrict_chat_member(
                        chat_id=group_id,
                        user_id=telegram_id,
                        permissions={
                            "can_send_messages": True,
                            "can_send_media_messages": True,
                            "can_send_polls": True,
                            "can_send_other_messages": True,
                            "can_add_web_page_previews": True,
                        }
                    )
                    logger.info(f"Unmuted user {telegram_id} in group {group_id}")
                except Exception as e:
                    logger.error(f"Failed to unmute user: {e}")
            
            if send_followup:
                success_msg = verification_success_message(mercle_user_id)
                keyboard = [
                    [InlineKeyboardButton(text="📥 Download Mercle (iOS)", url=self.config.mercle_ios_url)],
                    [InlineKeyboardButton(text="📥 Download Mercle (Android)", url=self.config.mercle_android_url)],
                ]
                await bot.send_message(chat_id=chat_id, text=success_msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
            elif panel_message_id:
                try:
                    await bot.edit_message_text(chat_id=chat_id, message_id=panel_message_id, text="✅ Verified.", parse_mode="HTML")
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"Error handling verification success: {e}", exc_info=True)
    
    async def _handle_failure(
        self,
        bot: Bot,
        session_id: str,
        chat_id: int,
        group_id: Optional[int],
        telegram_id: int,
        action_on_timeout: str,
        *,
        send_followup: bool = True,
        panel_message_id: Optional[int] = None,
        pending_kind: Optional[str] = None,
    ):
        """Handle failed verification."""
        try:
            logger.warning(f"❌ Verification failed for session {session_id}")
            
            # Get session details
            session_obj = await self.user_manager.get_session(session_id)
            
            # Delete verification messages (skip for panel flows)
            if send_followup and session_obj and session_obj.message_ids:
                await self._delete_messages(bot, chat_id, session_obj.message_ids)
            
            # Update session status
            await self.user_manager.update_session_status(session_id, "rejected")
            
            # If this was for a group, apply configured action (skip for join-request gating).
            if group_id and pending_kind != "join_request":
                await self._handle_group_action(bot, group_id, telegram_id, action_on_timeout)
            
            if send_followup:
                await bot.send_message(chat_id=chat_id, text=verification_failed_message(), parse_mode="Markdown")
            elif panel_message_id:
                try:
                    await bot.edit_message_text(chat_id=chat_id, message_id=panel_message_id, text="❌ Verification failed.", parse_mode="HTML")
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"Error handling verification failure: {e}", exc_info=True)
    
    async def _handle_timeout(
        self,
        bot: Bot,
        session_id: str,
        chat_id: int,
        group_id: Optional[int],
        telegram_id: int,
        action_on_timeout: str,
        *,
        send_followup: bool = True,
        panel_message_id: Optional[int] = None,
        pending_kind: Optional[str] = None,
    ):
        """Handle verification timeout."""
        try:
            logger.warning(f"⏰ Verification timeout for session {session_id}")
            
            # Get session details
            session_obj = await self.user_manager.get_session(session_id)
            
            # Delete verification messages (skip for panel flows)
            if send_followup and session_obj and session_obj.message_ids:
                await self._delete_messages(bot, chat_id, session_obj.message_ids)
            
            # Update session status
            await self.user_manager.update_session_status(session_id, "expired")
            
            # If this was for a group, take action based on setting (skip for join-request gating).
            if group_id and pending_kind != "join_request":
                await self._handle_group_action(bot, group_id, telegram_id, action_on_timeout)
            
            if send_followup:
                await bot.send_message(chat_id=chat_id, text=verification_timeout_message(), parse_mode="Markdown")
            elif panel_message_id:
                try:
                    await bot.edit_message_text(chat_id=chat_id, message_id=panel_message_id, text="⏱ Timed out.", parse_mode="HTML")
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"Error handling verification timeout: {e}", exc_info=True)
    
    async def _delete_messages(self, bot: Bot, chat_id: int, message_ids_str: str):
        """Delete verification messages."""
        try:
            message_ids = [int(mid) for mid in message_ids_str.split(",") if mid.strip()]
            for msg_id in message_ids:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as e:
                    logger.debug(f"Could not delete message {msg_id}: {e}")
        except Exception as e:
            logger.error(f"Error deleting messages: {e}")
    
    async def _handle_group_action(self, bot: Bot, group_id: int, telegram_id: int, action: str):
        """Handle group action (kick or mute) on verification failure/timeout."""
        try:
            if action == "kick":
                await bot.ban_chat_member(chat_id=group_id, user_id=telegram_id)
                await bot.unban_chat_member(chat_id=group_id, user_id=telegram_id)
                logger.info(f"Kicked user {telegram_id} from group {group_id}")
            elif action == "mute":
                await bot.restrict_chat_member(
                    chat_id=group_id,
                    user_id=telegram_id,
                    permissions=ChatPermissions(
                        can_send_messages=False,
                        can_send_media_messages=False,
                        can_send_polls=False,
                        can_send_other_messages=False,
                        can_add_web_page_previews=False,
                    ),
                )
                logger.info(f"Muted user {telegram_id} in group {group_id}")
        except Exception as e:
            logger.error(f"Failed to {action} user {telegram_id}: {e}")
    
    def cancel_verification(self, session_id: str):
        """Cancel an active verification."""
        if session_id in self.active_verifications:
            task = self.active_verifications[session_id]
            task.cancel()
            logger.info(f"Cancelled verification for session {session_id}")
