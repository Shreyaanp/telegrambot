"""Webhook server for production deployment with FastAPI."""
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from aiogram.types import Update
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

from bot.core.bot import TelegramBot
from bot.config import Config
from bot.services.mercle_sdk import MercleSDK
from bot.services.session_service import SessionService
from database import init_database, get_database

# Import all plugins
from bot.plugins.verification import VerificationPlugin
from bot.plugins.admin import AdminPlugin
from bot.plugins.warnings import WarningsPlugin
from bot.plugins.whitelist import WhitelistPlugin
from bot.plugins.rules import RulesPlugin
from bot.plugins.stats import StatsPlugin
from bot.plugins.antiflood import AntiFloodPlugin
from bot.plugins.greetings import GreetingsPlugin
from bot.plugins.filters import FiltersPlugin
from bot.plugins.locks import LocksPlugin
from bot.plugins.notes import NotesPlugin
from bot.plugins.admin_logs import AdminLogsPlugin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global bot instance
telegram_bot: TelegramBot = None
config = Config.from_env()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global telegram_bot
    
    logger.info("🚀 Starting Webhook Server...")
    
    try:
        # Initialize bot
        telegram_bot = TelegramBot(config)
        await telegram_bot.initialize()
        
        # Initialize Mercle SDK
        mercle_sdk = MercleSDK(
            api_url=config.mercle_api_url,
            api_key=config.mercle_api_key
        )
        
        # Register services
        telegram_bot.get_plugin_manager().register_service("mercle_sdk", mercle_sdk)
        
        # Load all plugins
        plugin_classes = [
            VerificationPlugin,
            AdminPlugin,
            WarningsPlugin,
            WhitelistPlugin,
            RulesPlugin,
            StatsPlugin,
            AntiFloodPlugin,
            GreetingsPlugin,
            FiltersPlugin,
            LocksPlugin,
            NotesPlugin,
            AdminLogsPlugin,
        ]
        await telegram_bot.load_plugins(plugin_classes)
        
        # Start bot
        await telegram_bot.start()
        
        # Register all commands in Telegram UI
        from aiogram.types import BotCommand
        commands = [
            BotCommand(command="start", description="Start the bot"),
            BotCommand(command="help", description="Show all commands and features"),
            BotCommand(command="verify", description="Verify your identity with biometrics"),
            BotCommand(command="status", description="Check your verification status"),
            BotCommand(command="settings", description="View/change group settings (admin)"),
            BotCommand(command="vverify", description="Manually verify a user (admin)"),
            BotCommand(command="vunverify", description="Remove user's verification (admin)"),
            BotCommand(command="kick", description="Kick a user from the group (admin)"),
            BotCommand(command="ban", description="Ban a user from the group (admin)"),
            BotCommand(command="unban", description="Unban a user (admin)"),
            BotCommand(command="mute", description="Mute a user (admin)"),
            BotCommand(command="unmute", description="Unmute a user (admin)"),
            BotCommand(command="warn", description="Warn a user (admin)"),
            BotCommand(command="warns", description="Check user's warnings"),
            BotCommand(command="resetwarns", description="Reset user's warnings (admin)"),
            BotCommand(command="whitelist", description="Add user to whitelist (admin)"),
            BotCommand(command="unwhitelist", description="Remove from whitelist (admin)"),
            BotCommand(command="rules", description="Show group rules"),
            BotCommand(command="setrules", description="Set group rules (admin)"),
            BotCommand(command="stats", description="Show verification statistics"),
        ]
        await telegram_bot.get_bot().set_my_commands(commands)
        logger.info(f"✅ Registered {len(commands)} commands in Telegram UI")
        
        # Set webhook
        webhook_url = f"{config.webhook_url}{config.webhook_path}"
        await telegram_bot.get_bot().set_webhook(
            url=webhook_url,
            allowed_updates=telegram_bot.get_dispatcher().resolve_used_update_types()
        )
        logger.info(f"✅ Webhook set to: {webhook_url}")
        
        # Start periodic cleanup task
        cleanup_task = asyncio.create_task(periodic_cleanup())
        
        yield
        
        # Shutdown
        logger.info("🛑 Shutting down Webhook Server...")
        cleanup_task.cancel()
        await telegram_bot.get_bot().delete_webhook()
        await telegram_bot.stop()
        
    except Exception as e:
        logger.error(f"❌ Failed to start webhook server: {e}", exc_info=True)
        raise


async def periodic_cleanup():
    """Periodically cleanup expired sessions."""
    while True:
        try:
            await asyncio.sleep(60)  # Run every minute
            
            db = get_database()
            session_service = SessionService(db)
            count = await session_service.cleanup_expired_sessions()
            
            if count > 0:
                logger.info(f"🧹 Cleaned up {count} expired sessions")
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")


# Create FastAPI app
app = FastAPI(lifespan=lifespan, title="Telegram Verification Bot")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post(config.webhook_path)
async def webhook_handler(request: Request):
    """Handle incoming webhook updates from Telegram."""
    try:
        update_data = await request.json()
        update = Update(**update_data)
        
        # Process update
        await telegram_bot.get_dispatcher().feed_update(
            telegram_bot.get_bot(),
            update
        )
        
        return Response(status_code=200)
        
    except Exception as e:
        logger.error(f"Error processing webhook update: {e}", exc_info=True)
        return Response(status_code=500)


@app.get("/verify")
async def verify_redirect(
    session_id: str,
    app_name: str,
    app_domain: str
):
    """Serve the deep link redirect page."""
    try:
        # Read the verify.html file
        with open("static/verify.html", "r") as f:
            html_content = f.read()
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error serving verify page: {e}")
        return HTMLResponse(
            content="<html><body><h1>Error loading verification page</h1></body></html>",
            status_code=500
        )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        if telegram_bot:
            health = await telegram_bot.health_check()
            return {
                "status": "healthy",
                "bot": health.get("bot", False),
                "database": health.get("database", False),
                "plugins": health.get("plugins", {})
            }
        else:
            return {"status": "initializing"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


@app.get("/status")
async def status():
    """Status endpoint with plugin information."""
    try:
        if telegram_bot:
            plugin_manager = telegram_bot.get_plugin_manager()
            status_info = plugin_manager.get_status()
            
            # Add database stats
            db = telegram_bot.get_database()
            table_counts = await db.get_table_counts()
            
            return {
                "status": "running",
                "plugins": status_info,
                "database": table_counts
            }
        else:
            return {"status": "initializing"}
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Telegram Verification Bot",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "webhook": config.webhook_path,
            "health": "/health",
            "status": "/status",
            "verify": "/verify"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
