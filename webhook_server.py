"""Webhook server for production deployment - clean architecture."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from aiogram.types import Update

from bot.main import TelegramBot
from bot.config import Config
from bot.services.user_manager import UserManager

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
        await telegram_bot.start()
        
        # Set webhook
        webhook_url = f"{config.webhook_url}{config.webhook_path}"
        await telegram_bot.get_bot().set_webhook(
            url=webhook_url,
            allowed_updates=telegram_bot.get_dispatcher().resolve_used_update_types()
        )
        logger.info(f"✅ Webhook set to: {webhook_url}")

        yield
        
        # Shutdown
        logger.info("🛑 Shutting down Webhook Server...")
        await telegram_bot.get_bot().delete_webhook()
        await telegram_bot.stop()
        
    except Exception as e:
        logger.error(f"❌ Failed to start webhook server: {e}", exc_info=True)
        raise


# Create FastAPI app
app = FastAPI(
    lifespan=lifespan,
    title="Telegram Verification Bot",
    description="Biometric verification bot powered by Mercle SDK",
    version="2.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post(config.webhook_path)
async def webhook_handler(request: Request):
    """
    Handle incoming webhook updates from Telegram.
    
    This is called by Telegram whenever there's a new message, command, or event.
    """
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
        logger.error(f"❌ Error processing webhook update: {e}", exc_info=True)
        try:
            if telegram_bot and telegram_bot.get_container():
                await telegram_bot.get_container().metrics_service.incr_api_error("webhook_update")
        except Exception:
            pass
        return Response(status_code=500)


@app.get("/verify")
async def verify_redirect(
    session_id: str,
    app_name: str,
    app_domain: str,
    base64_qr: str = ""
):
    """
    Serve the deep link redirect page.
    
    This page automatically redirects to the Mercle app with the verification data.
    """
    try:
        # Read the verify.html file
        with open("static/verify.html", "r") as f:
            html_content = f.read()
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error serving verify page: {e}")
        return HTMLResponse(
            content="""
            <html>
                <head><title>Error</title></head>
                <body>
                    <h1>Error loading verification page</h1>
                    <p>Please try again or contact support.</p>
                </body>
            </html>
            """,
            status_code=500
        )


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns the health status of the bot and its components.
    """
    try:
        if telegram_bot and telegram_bot.is_running():
            # Try to get bot info to verify it's working
            bot_info = await telegram_bot.get_bot().get_me()
            
            return {
                "status": "healthy",
                "bot": {
                    "username": bot_info.username,
                    "id": bot_info.id,
                    "running": True
                },
                "database": "connected",
                "version": "2.0.0"
            }
        else:
            return {
                "status": "initializing",
                "message": "Bot is starting up..."
            }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.get("/status")
async def status():
    """
    Status endpoint with detailed information.
    
    Returns statistics and configuration details.
    """
    try:
        if telegram_bot and telegram_bot.is_running():
            container = telegram_bot.get_container()
            
            # Get some basic stats
            from database.db import db
            from database.models import User, VerificationSession
            from sqlalchemy import select, func
            admin_actions, verification_outcomes, api_errors, last_update_at = await container.metrics_service.snapshot()
            
            async with db.session() as session:
                # Count verified users
                user_count = await session.execute(select(func.count(User.telegram_id)))
                total_users = user_count.scalar()
                
                # Count active sessions
                session_count = await session.execute(
                    select(func.count(VerificationSession.session_id))
                    .where(VerificationSession.status == "pending")
                )
                active_sessions = session_count.scalar()
            
            return {
                "status": "running",
                "version": "2.0.0",
                "stats": {
                    "total_verified_users": total_users,
                    "active_verification_sessions": active_sessions,
                    "admin_actions": admin_actions,
                    "verification_outcomes": verification_outcomes,
                    "api_errors": api_errors,
                    "last_update_at": last_update_at.isoformat() if last_update_at else None,
                },
                "config": {
                    "verification_timeout_minutes": container.config.timeout_minutes,
                    "action_on_timeout": container.config.action_on_timeout,
                    "auto_delete_messages": container.config.auto_delete_verification_messages
                }
            }
        else:
            return {
                "status": "initializing",
                "message": "Bot is starting up..."
            }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/")
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "name": "Telegram Verification Bot",
        "description": "Biometric verification bot powered by Mercle SDK",
        "version": "2.0.0",
        "status": "running" if telegram_bot and telegram_bot.is_running() else "initializing",
        "endpoints": {
            "webhook": config.webhook_path,
            "health": "/health",
            "status": "/status",
            "verify": "/verify"
        },
        "documentation": {
            "commands": "/help",
            "support": "support@mercle.ai"
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
