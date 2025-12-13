"""Command handlers for the bot."""
import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.services.verification import VerificationService
from bot.services.user_manager import UserManager
from bot.utils.messages import (
    welcome_message,
    already_verified_message,
    help_message,
    status_message,
)

logger = logging.getLogger(__name__)

router = Router()


async def cmd_start(
    message: Message,
    user_manager: UserManager,
    verification_service: VerificationService
):
    """Handle /start command."""
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Check if already verified
    is_verified = await user_manager.is_verified(user_id)
    
    if is_verified:
        await message.answer(already_verified_message(), parse_mode="Markdown")
    else:
        await message.answer(welcome_message(username), parse_mode="Markdown")
    
    logger.info(f"User {user_id} ({username}) used /start")


async def cmd_verify(
    message: Message,
    user_manager: UserManager,
    verification_service: VerificationService
):
    """Handle /verify command."""
    user_id = message.from_user.id
    username = message.from_user.username
    chat_id = message.chat.id
    
    # Check if already verified
    is_verified = await user_manager.is_verified(user_id)
    
    if is_verified:
        await message.answer(already_verified_message(), parse_mode="Markdown")
        return
    
    # Start verification
    success = await verification_service.start_verification(
        bot=message.bot,
        telegram_id=user_id,
        chat_id=chat_id,
        username=username
    )
    
    if not success:
        await message.answer(
            "❌ Failed to start verification. Please try again later.",
            parse_mode="Markdown"
        )
    
    logger.info(f"User {user_id} ({username}) used /verify")


async def cmd_status(message: Message, user_manager: UserManager):
    """Handle /status command."""
    user_id = message.from_user.id
    
    # Check verification status
    user = await user_manager.get_user(user_id)
    
    if user:
        msg = status_message(True, user.mercle_user_id)
    else:
        msg = status_message(False)
    
    await message.answer(msg, parse_mode="Markdown")
    logger.info(f"User {user_id} checked /status")


async def cmd_help(message: Message):
    """Handle /help command."""
    await message.answer(help_message(), parse_mode="Markdown")
    logger.info(f"User {message.from_user.id} used /help")


def register_command_handlers(router: Router):
    """Register all command handlers."""
    router.message.register(cmd_start, CommandStart())
    router.message.register(cmd_verify, Command("verify"))
    router.message.register(cmd_status, Command("status"))
    router.message.register(cmd_help, Command("help"))

