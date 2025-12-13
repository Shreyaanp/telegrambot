"""Main bot entry point - polling mode for local development."""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from bot.config import Config
from bot.services.mercle_sdk import MercleSDK
from bot.services.user_manager import UserManager
from bot.services.verification import VerificationService
from bot.handlers import commands, member_events
from database.db import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Start the bot in polling mode."""
    try:
        # Load configuration
        config = Config.from_env()
        logger.info("✅ Configuration loaded")
        
        # Initialize database
        await db.create_tables()
        logger.info("✅ Database initialized")
        
        # Initialize services
        mercle_sdk = MercleSDK(config.mercle_api_url, config.mercle_api_key)
        user_manager = UserManager()
        verification_service = VerificationService(config, mercle_sdk, user_manager)
        logger.info("✅ Services initialized")
        
        # Initialize bot and dispatcher
        bot = Bot(
            token=config.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher()
        
        # Store services in bot data for access in handlers
        bot_data = {
            "user_manager": user_manager,
            "verification_service": verification_service,
            "config": config
        }
        
        # Register command handlers
        from aiogram.filters import CommandStart, Command
        
        async def cmd_start_wrapper(message, **kwargs):
            await commands.cmd_start(message, user_manager, verification_service)
        
        async def cmd_verify_wrapper(message, **kwargs):
            await commands.cmd_verify(message, user_manager, verification_service)
        
        async def cmd_status_wrapper(message, **kwargs):
            await commands.cmd_status(message, user_manager)
        
        async def cmd_help_wrapper(message, **kwargs):
            await commands.cmd_help(message)
        
        dp.message.register(cmd_start_wrapper, CommandStart())
        dp.message.register(cmd_verify_wrapper, Command("verify"))
        dp.message.register(cmd_status_wrapper, Command("status"))
        dp.message.register(cmd_help_wrapper, Command("help"))
        
        # Register member event handler
        async def on_new_member_wrapper(event, **kwargs):
            await member_events.on_new_member(event, user_manager, verification_service, config)
        
        from aiogram.filters import ChatMemberUpdatedFilter, MEMBER, RESTRICTED, LEFT, KICKED
        dp.chat_member.register(
            on_new_member_wrapper,
            ChatMemberUpdatedFilter(member_status_changed=(LEFT | KICKED) >> (MEMBER | RESTRICTED))
        )
        
        logger.info("✅ Handlers registered")
        
        # Start polling
        logger.info("🤖 Starting bot in polling mode...")
        logger.info(f"📱 Bot username: @mercleMerci_bot")
        logger.info(f"🔗 Mercle API: {config.mercle_api_url}")
        logger.info(f"⏰ Verification timeout: {config.verification_timeout}s")
        
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        raise
    finally:
        # Cleanup
        await db.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")

