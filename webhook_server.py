"""
FastAPI webhook server for Telegram bot.
Production-ready with health checks and proper error handling.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command, ChatMemberUpdatedFilter, MEMBER, RESTRICTED, LEFT, KICKED

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

# Global bot and services
bot_instance = None
dispatcher = None
user_manager = None
verification_service = None
config = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global bot_instance, dispatcher, user_manager, verification_service, config
    
    # Startup
    logger.info("🚀 Starting webhook server...")
    
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
    bot_instance = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dispatcher = Dispatcher()
    
    # Register command handlers
    async def cmd_start_wrapper(message, **kwargs):
        await commands.cmd_start(message, user_manager, verification_service)
    
    async def cmd_verify_wrapper(message, **kwargs):
        await commands.cmd_verify(message, user_manager, verification_service)
    
    async def cmd_status_wrapper(message, **kwargs):
        await commands.cmd_status(message, user_manager)
    
    async def cmd_help_wrapper(message, **kwargs):
        await commands.cmd_help(message)
    
    dispatcher.message.register(cmd_start_wrapper, CommandStart())
    dispatcher.message.register(cmd_verify_wrapper, Command("verify"))
    dispatcher.message.register(cmd_status_wrapper, Command("status"))
    dispatcher.message.register(cmd_help_wrapper, Command("help"))
    
    # Register member event handler
    async def on_new_member_wrapper(event, **kwargs):
        await member_events.on_new_member(event, user_manager, verification_service, config)
    
    dispatcher.chat_member.register(
        on_new_member_wrapper,
        ChatMemberUpdatedFilter(member_status_changed=(LEFT | KICKED) >> (MEMBER | RESTRICTED))
    )
    
    logger.info("✅ Handlers registered")
    
    # Set webhook
    webhook_url = f"{config.webhook_url}{config.webhook_path}"
    await bot_instance.set_webhook(
        url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=dispatcher.resolve_used_update_types()
    )
    logger.info(f"✅ Webhook set to: {webhook_url}")
    logger.info(f"🤖 Bot @mercleMerci_bot is ready!")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down webhook server...")
    await bot_instance.delete_webhook()
    await bot_instance.session.close()
    await db.close()
    logger.info("✅ Cleanup complete")


app = FastAPI(lifespan=lifespan, title="Telegram Verification Bot")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "bot": "Telegram Verification Bot with Mercle SDK",
        "status": "running",
        "mode": "webhook"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "bot": "online",
        "database": "connected"
    }


@app.post("/webhook/{secret_path}")
async def telegram_webhook(request: Request, secret_path: str) -> Response:
    """
    Handle incoming webhook updates from Telegram.
    Path is dynamic and comes from WEBHOOK_PATH env var.
    """
    global bot_instance, dispatcher, config
    
    if not bot_instance or not dispatcher:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    # Verify the webhook path matches (strip leading slash for comparison)
    expected_path = config.webhook_path.lstrip("/").replace("webhook/", "")
    if secret_path != expected_path:
        logger.warning(f"Invalid webhook path attempted: {secret_path}, expected: {expected_path}")
        raise HTTPException(status_code=404, detail="Not found")
    
    try:
        # Parse update from Telegram
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot_instance})
        
        # Feed update to dispatcher
        await dispatcher.feed_update(bot_instance, update)
        
        return Response(status_code=200)
        
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
        # Return 200 anyway to prevent Telegram from retrying
        return Response(status_code=200)


@app.get("/webhook/info")
async def webhook_info():
    """Get current webhook information."""
    global bot_instance
    
    if not bot_instance:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    try:
        webhook_info = await bot_instance.get_webhook_info()
        return {
            "url": webhook_info.url,
            "has_custom_certificate": webhook_info.has_custom_certificate,
            "pending_update_count": webhook_info.pending_update_count,
            "last_error_date": webhook_info.last_error_date,
            "last_error_message": webhook_info.last_error_message,
            "max_connections": webhook_info.max_connections,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

