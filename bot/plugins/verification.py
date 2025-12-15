"""Verification plugin - handles user verification via Mercle SDK."""
import asyncio
import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional
from aiogram import F
from aiogram.types import Message, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command, ChatMemberUpdatedFilter, MEMBER, RESTRICTED, LEFT, KICKED
from aiogram.enums import ChatType, ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

from bot.plugins.base import BasePlugin
from bot.services import (
    UserService,
    GroupService,
    SessionService,
    PermissionService,
    MessageCleanerService,
    MercleSDK
)
from bot.utils.qr_generator import generate_qr_code, decode_base64_qr
from bot.utils.messages import (
    verification_prompt_message,
    verification_success_message,
    verification_timeout_message,
    verification_failed_message,
    already_verified_message,
    welcome_message,
    status_message
)

logger = logging.getLogger(__name__)


class VerificationPlugin(BasePlugin):
    """Plugin for handling user verification flows."""
    
    @property
    def name(self) -> str:
        return "verification"
    
    @property
    def description(self) -> str:
        return "Auto-verification on group join + manual /verify command"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        
        # Initialize services
        self.user_service = UserService(db)
        self.group_service = GroupService(db)
        self.session_service = SessionService(db)
        self.permission_service = PermissionService(db)
        self.message_cleaner = MessageCleanerService()
        self.mercle_sdk: MercleSDK = services.get("mercle_sdk")
        
        # Track active verification tasks
        self.active_tasks = {}
    
    async def on_load(self):
        """Register handlers when plugin is loaded."""
        await super().on_load()
        
        # Register command handlers
        self.router.message.register(self.cmd_start, Command("start"))
        self.router.message.register(self.cmd_verify, Command("verify"))
        self.router.message.register(self.cmd_status, Command("status"))
        self.router.message.register(self.cmd_help, Command("help"))
        
        # Register chat member update handler (for group joins)
        self.router.chat_member.register(
            self.on_new_member_join,
            ChatMemberUpdatedFilter(member_status_changed=(LEFT | KICKED) >> (MEMBER | RESTRICTED))
        )
        
        self.logger.info("Verification plugin loaded successfully")
    
    def get_commands(self):
        return [
            {"command": "/start", "description": "Start the bot"},
            {"command": "/verify", "description": "Verify your identity"},
            {"command": "/status", "description": "Check verification status"},
            {"command": "/help", "description": "Show help message"},
        ]
    
    # Command Handlers
    
    async def cmd_start(self, message: Message):
        """Handle /start command."""
        user = message.from_user
        
        # Check if already verified
        is_verified = await self.user_service.is_verified(user.id)
        
        if is_verified:
            await message.answer(already_verified_message())
        else:
            await message.answer(welcome_message(user.username))
    
    async def cmd_verify(self, message: Message):
        """Handle /verify command (manual verification)."""
        user = message.from_user
        chat_id = message.chat.id
        
        # Check if already verified
        is_verified = await self.user_service.is_verified(user.id)
        if is_verified:
            await message.answer(already_verified_message())
            return
        
        # Check if there's already an active session
        active_session = await self.session_service.get_active_session(user.id)
        if active_session:
            await message.answer("⚠️ You already have an active verification session. Please complete it first.")
            return
        
        # Start verification
        await self._start_verification_flow(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            chat_id=chat_id,
            group_id=None,
            trigger_type="manual_command"
        )
    
    async def cmd_status(self, message: Message):
        """Handle /status command."""
        user = message.from_user
        
        user_obj = await self.user_service.get_user(user.id)
        if user_obj:
            await message.answer(status_message(True, user_obj.mercle_user_id))
        else:
            await message.answer(status_message(False))
    
    async def cmd_help(self, message: Message):
        """Handle /help command."""
        from bot.utils.messages import help_message
        await message.answer(help_message(), parse_mode="Markdown")
    
    # Group Join Handler
    
    async def on_new_member_join(self, event: ChatMemberUpdated):
        """Handle new member joining a group."""
        new_member = event.new_chat_member.user
        chat = event.chat
        
        # Skip if it's a bot
        if new_member.is_bot:
            self.logger.info(f"Bot {new_member.username} added to group {chat.id}")
            return
        
        # Skip if not a group
        if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            return
        
        user_id = new_member.id
        username = new_member.username
        group_id = chat.id
        group_name = chat.title or "this group"
        
        self.logger.info(f"New member {user_id} ({username}) joined group {group_id}")
        
        # Ensure group exists in database
        group = await self.group_service.get_group(group_id)
        if not group:
            group = await self.group_service.create_group(
                group_id=group_id,
                group_name=group_name,
                verification_timeout=self.config.verification_timeout
            )
        
        # Check if auto-verification is enabled for this group
        if not group.auto_verify_on_join:
            self.logger.info(f"Auto-verification disabled for group {group_id}")
            return
        
        # Check if user is whitelisted
        is_whitelisted = await self.permission_service.is_whitelisted(group_id, user_id)
        if is_whitelisted:
            self.logger.info(f"User {user_id} is whitelisted in group {group_id}, skipping verification")
            await self.group_service.add_member(group_id, user_id, verified=True, muted=False)
            return
        
        # Check if user is already globally verified
        is_verified = await self.user_service.is_verified(user_id)
        if is_verified:
            self.logger.info(f"User {user_id} is already globally verified")
            await self.group_service.add_member(group_id, user_id, verified=True, muted=False)
            # Send welcome back message
            try:
                await self.bot.send_message(
                    chat_id=group_id,
                    text=f"👋 Welcome back {username or 'user'}! You're already verified. ✅"
                )
            except:
                pass
            return
        
        # User needs verification - mute them
        try:
            await self.bot.restrict_chat_member(
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
            self.logger.info(f"Muted user {user_id} in group {group_id}")
            
            # Add member to database as muted
            await self.group_service.add_member(group_id, user_id, verified=False, muted=True)
            
        except TelegramBadRequest as e:
            self.logger.error(f"Failed to mute user {user_id} in group {group_id}: {e}")
            return
        
        # Determine where to send verification based on group settings
        verification_location = group.verification_location if group else "group"
        
        if verification_location == "dm":
            # Send notice in group, verification in DM
            try:
                from bot.utils.messages import verification_dm_notice_message
                await self.bot.send_message(
                    chat_id=group_id,
                    text=verification_dm_notice_message(group_name),
                    parse_mode="Markdown"
                )
            except:
                pass
            
            # Start verification in DM
            await self._start_verification_flow(
                telegram_id=user_id,
                username=username,
                first_name=new_member.first_name,
                last_name=new_member.last_name,
                chat_id=user_id,  # Send to DM
                group_id=group_id,
                trigger_type="auto_join"
            )
        else:
            # Send verification in group (default behavior)
            await self._start_verification_flow(
                telegram_id=user_id,
                username=username,
                first_name=new_member.first_name,
                last_name=new_member.last_name,
                chat_id=group_id,  # Send in group
                group_id=group_id,
                trigger_type="auto_join"
            )
    
    # Verification Flow
    
    async def _start_verification_flow(
        self,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        chat_id: int,
        group_id: Optional[int],
        trigger_type: str
    ):
        """Start the verification flow for a user."""
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
            qr_data = sdk_response.get("qr_data", "")
            
            # Get group settings for timeout
            timeout = self.config.verification_timeout
            if group_id:
                group = await self.group_service.get_group(group_id)
                if group:
                    timeout = group.verification_timeout
            
            # Save session to database
            expires_at = datetime.utcnow() + timedelta(seconds=timeout)
            await self.session_service.create_session(
                session_id=session_id,
                telegram_id=telegram_id,
                chat_id=chat_id,
                expires_at=expires_at,
                group_id=group_id,
                trigger_type=trigger_type,
                message_ids=[]
            )
            
            # Generate QR code
            qr_json = decode_base64_qr(base64_qr) if base64_qr else qr_data
            qr_image = generate_qr_code(qr_json) if qr_json else None
            
            # Create universal link for deep link
            universal_link = f" https://telegram.mercle.ai/verify?session_id={session_id}&app_name={urllib.parse.quote('Telegram Verification Bot')}&app_domain={urllib.parse.quote('telegram.mercle.ai')}"
            
            # Build inline keyboard
            keyboard = [
                [InlineKeyboardButton(text="📱 Open Mercle App", url=universal_link)],
                [InlineKeyboardButton(text="📥 Get Mercle (iOS)", url="https://apps.apple.com/ng/app/mercle/id6751991316")],
                [InlineKeyboardButton(text="📥 Get Mercle (Android)", url="https://play.google.com/store/apps/details?id=com.mercle.app")]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            
            # Send verification message
            message_text = verification_prompt_message(timeout)
            
            sent_message = None
            if qr_image:
                qr_file = BufferedInputFile(qr_image.read(), filename="qr_code.png")
                sent_message = await self.bot.send_photo(
                    chat_id=chat_id,
                    photo=qr_file,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                sent_message = await self.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            # Store message ID
            if sent_message:
                await self.session_service.store_message_ids(session_id, [sent_message.message_id])
            
            # Start polling task
            task = asyncio.create_task(
                self._poll_verification_status(
                    session_id=session_id,
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    chat_id=chat_id,
                    group_id=group_id,
                    timeout=timeout
                )
            )
            self.active_tasks[session_id] = task
            
            self.logger.info(f"Started verification flow for user {telegram_id}, session: {session_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to start verification flow: {e}", exc_info=True)
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Failed to start verification. Please try again later."
                )
            except:
                pass
    
    async def _poll_verification_status(
        self,
        session_id: str,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        chat_id: int,
        group_id: Optional[int],
        timeout: int
    ):
        """Poll Mercle SDK for verification status."""
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
                        session_id=session_id,
                        telegram_id=telegram_id,
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        mercle_user_id=mercle_user_id,
                        chat_id=chat_id,
                        group_id=group_id
                    )
                    return
                
                elif status in ["rejected", "expired"]:
                    # Verification failed
                    await self._handle_verification_failure(
                        session_id=session_id,
                        telegram_id=telegram_id,
                        chat_id=chat_id,
                        group_id=group_id
                    )
                    return
            
            # Timeout reached
            await self._handle_verification_timeout(
                session_id=session_id,
                telegram_id=telegram_id,
                chat_id=chat_id,
                group_id=group_id
            )
            
        except Exception as e:
            self.logger.error(f"Error polling verification: {e}", exc_info=True)
        finally:
            # Clean up
            if session_id in self.active_tasks:
                del self.active_tasks[session_id]
    
    async def _handle_verification_success(
        self,
        session_id: str,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        mercle_user_id: str,
        chat_id: int,
        group_id: Optional[int]
    ):
        """Handle successful verification."""
        try:
            # Get message IDs to delete
            message_ids = await self.session_service.get_message_ids(session_id)
            
            # Delete verification messages
            if message_ids:
                await self.message_cleaner.delete_messages(self.bot, chat_id, message_ids)
            
            # Create/update user in database
            await self.user_service.create_user(
                telegram_id=telegram_id,
                mercle_user_id=mercle_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            
            # Update session status
            await self.session_service.update_status(session_id, "approved")
            
            # If group verification, unmute user
            if group_id:
                try:
                    # Unmute user
                    await self.bot.restrict_chat_member(
                        chat_id=group_id,
                        user_id=telegram_id,
                        permissions={
                            "can_send_messages": True,
                            "can_send_media_messages": True,
                            "can_send_polls": True,
                            "can_send_other_messages": True,
                            "can_add_web_page_previews": True,
                            "can_invite_users": True,
                            "can_pin_messages": False,
                            "can_change_info": False,
                        }
                    )
                    self.logger.info(f"Unmuted user {telegram_id} in group {group_id}")
                    
                    # Update member status
                    await self.group_service.update_member_verification(group_id, telegram_id, True)
                    await self.group_service.update_member_mute_status(group_id, telegram_id, False)
                    
                except TelegramBadRequest as e:
                    self.logger.error(f"Failed to unmute user {telegram_id} in group {group_id}: {e}")
            
            # Send success message with app promotion
            success_msg = verification_success_message(mercle_user_id)
            keyboard = [
                [InlineKeyboardButton(text="📥 Download Mercle (iOS)", url="https://apps.apple.com/ng/app/mercle/id6751991316")],
                [InlineKeyboardButton(text="📥 Download Mercle (Android)", url="https://play.google.com/store/apps/details?id=com.mercle.app")]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            
            await self.bot.send_message(
                chat_id=chat_id,
                text=success_msg,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            
            self.logger.info(f"✅ Verification successful for user {telegram_id}")
            
        except Exception as e:
            self.logger.error(f"Error handling verification success: {e}", exc_info=True)
    
    async def _handle_verification_failure(
        self,
        session_id: str,
        telegram_id: int,
        chat_id: int,
        group_id: Optional[int]
    ):
        """Handle failed verification."""
        try:
            # Get message IDs to delete
            message_ids = await self.session_service.get_message_ids(session_id)
            
            # Delete verification messages
            if message_ids:
                await self.message_cleaner.delete_messages(self.bot, chat_id, message_ids)
            
            # Update session status
            await self.session_service.update_status(session_id, "rejected")
            
            # Send failure message
            await self.bot.send_message(
                chat_id=chat_id,
                text=verification_failed_message(),
                parse_mode="Markdown"
            )
            
            self.logger.info(f"❌ Verification failed for user {telegram_id}")
            
        except Exception as e:
            self.logger.error(f"Error handling verification failure: {e}", exc_info=True)
    
    async def _handle_verification_timeout(
        self,
        session_id: str,
        telegram_id: int,
        chat_id: int,
        group_id: Optional[int]
    ):
        """Handle verification timeout."""
        try:
            # Get message IDs to delete
            message_ids = await self.session_service.get_message_ids(session_id)
            
            # Delete verification messages
            if message_ids:
                await self.message_cleaner.delete_messages(self.bot, chat_id, message_ids)
            
            # Update session status
            await self.session_service.update_status(session_id, "expired")
            
            # If group verification and kick_on_timeout is enabled, kick the user
            if group_id:
                group = await self.group_service.get_group(group_id)
                if group and group.kick_on_timeout:
                    try:
                        await self.bot.ban_chat_member(chat_id=group_id, user_id=telegram_id)
                        await self.bot.unban_chat_member(chat_id=group_id, user_id=telegram_id)  # Unban to allow rejoin
                        self.logger.info(f"Kicked user {telegram_id} from group {group_id} due to timeout")
                        
                        await self.bot.send_message(
                            chat_id=chat_id,
                            text="⏰ **Verification timed out.** User was removed from the group."
                        )
                        return
                    except TelegramBadRequest as e:
                        self.logger.error(f"Failed to kick user {telegram_id} from group {group_id}: {e}")
            
            # Send timeout message
            await self.bot.send_message(
                chat_id=chat_id,
                text=verification_timeout_message(),
                parse_mode="Markdown"
            )
            
            self.logger.info(f"⏰ Verification timeout for user {telegram_id}")
            
        except Exception as e:
            self.logger.error(f"Error handling verification timeout: {e}", exc_info=True)

