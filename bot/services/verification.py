"""Verification service - handles the complete verification flow."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from bot.config import Config
from bot.services.mercle_sdk import MercleSDK
from bot.services.user_manager import UserManager
from bot.utils.qr_generator import generate_qr_code, decode_base64_qr
from bot.utils.messages import (
    verification_prompt_message,
    verification_success_message,
    verification_timeout_message,
    verification_failed_message,
)

logger = logging.getLogger(__name__)


class VerificationService:
    """Handles verification flow with Mercle SDK."""
    
    def __init__(self, config: Config, mercle_sdk: MercleSDK, user_manager: UserManager):
        """Initialize verification service."""
        self.config = config
        self.mercle_sdk = mercle_sdk
        self.user_manager = user_manager
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
        
        Returns:
            True if verification started successfully, False otherwise
        """
        try:
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
            deep_link = sdk_response.get("deep_link", "")
            
            # Save session to database
            expires_at = datetime.utcnow() + timedelta(seconds=self.config.verification_timeout)
            await self.user_manager.create_session(
                session_id=session_id,
                telegram_id=telegram_id,
                expires_at=expires_at,
                telegram_username=username,
                group_id=group_id
            )
            
            # Generate QR code
            qr_data = decode_base64_qr(base64_qr) if base64_qr else ""
            qr_image = generate_qr_code(qr_data) if qr_data else None
            
            # Build inline keyboard with buttons
            keyboard = []
            
            # Add deep link button if available
            if deep_link:
                keyboard.append([
                    InlineKeyboardButton(
                        text="📱 Open Mercle App",
                        url=deep_link
                    )
                ])
            
            # Add download button
            keyboard.append([
                InlineKeyboardButton(
                    text="📥 Download Mercle App",
                    url="https://mercle.ai/download"
                )
            ])
            
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            
            # Send verification message with QR code
            message_text = verification_prompt_message(self.config.verification_timeout)
            
            if qr_image:
                qr_file = BufferedInputFile(qr_image.read(), filename="qr_code.png")
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=qr_file,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            # Start polling task
            task = asyncio.create_task(
                self._poll_verification(bot, session_id, telegram_id, chat_id)
            )
            self.active_verifications[session_id] = task
            
            logger.info(f"Started verification for user {telegram_id}, session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start verification: {e}", exc_info=True)
            return False
    
    async def _poll_verification(
        self,
        bot: Bot,
        session_id: str,
        telegram_id: int,
        chat_id: int
    ):
        """Poll Mercle SDK for verification status."""
        timeout = self.config.verification_timeout
        poll_interval = 3  # Check every 3 seconds
        max_polls = timeout // poll_interval
        
        try:
            for i in range(max_polls):
                await asyncio.sleep(poll_interval)
                
                # Check session status
                status_response = await self.mercle_sdk.check_status(session_id)
                status = status_response.get("status")
                
                if status == "approved":
                    # Verification successful!
                    mercle_user_id = status_response.get("localized_user_id")
                    await self._handle_verification_success(
                        bot, session_id, telegram_id, chat_id, mercle_user_id
                    )
                    return
                
                elif status in ["rejected", "expired"]:
                    # Verification failed
                    await self._handle_verification_failure(bot, session_id, chat_id)
                    return
            
            # Timeout reached
            await self._handle_verification_timeout(bot, session_id, chat_id)
            
        except Exception as e:
            logger.error(f"Error polling verification: {e}", exc_info=True)
        finally:
            # Clean up
            if session_id in self.active_verifications:
                del self.active_verifications[session_id]
    
    async def _handle_verification_success(
        self,
        bot: Bot,
        session_id: str,
        telegram_id: int,
        chat_id: int,
        mercle_user_id: str
    ):
        """Handle successful verification."""
        try:
            # Get session to find username
            session_obj = await self.user_manager.get_session(session_id)
            username = session_obj.telegram_username if session_obj else None
            
            # Create/update user in database
            await self.user_manager.create_user(
                telegram_id=telegram_id,
                mercle_user_id=mercle_user_id,
                username=username
            )
            
            # Update session status
            await self.user_manager.update_session_status(session_id, "approved")
            
            # Send success message
            success_msg = verification_success_message(mercle_user_id)
            await bot.send_message(chat_id=chat_id, text=success_msg, parse_mode="Markdown")
            
            logger.info(f"Verification successful for user {telegram_id}")
            
        except Exception as e:
            logger.error(f"Error handling verification success: {e}", exc_info=True)
    
    async def _handle_verification_failure(self, bot: Bot, session_id: str, chat_id: int):
        """Handle failed verification."""
        await self.user_manager.update_session_status(session_id, "rejected")
        await bot.send_message(
            chat_id=chat_id,
            text=verification_failed_message(),
            parse_mode="Markdown"
        )
        logger.info(f"Verification failed for session {session_id}")
    
    async def _handle_verification_timeout(self, bot: Bot, session_id: str, chat_id: int):
        """Handle verification timeout."""
        await self.user_manager.update_session_status(session_id, "expired")
        await bot.send_message(
            chat_id=chat_id,
            text=verification_timeout_message(),
            parse_mode="Markdown"
        )
        logger.info(f"Verification timeout for session {session_id}")

