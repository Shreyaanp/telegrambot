"""Webhook server for production deployment - clean architecture."""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from aiogram.types import Update

from bot.main import TelegramBot
from bot.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global bot instance
telegram_bot: TelegramBot = None
config = Config.from_env()

def _update_kind(update: Update) -> str:
    if getattr(update, "message", None) is not None:
        return "message"
    if getattr(update, "edited_message", None) is not None:
        return "edited_message"
    if getattr(update, "callback_query", None) is not None:
        return "callback_query"
    if getattr(update, "chat_join_request", None) is not None:
        return "chat_join_request"
    if getattr(update, "my_chat_member", None) is not None:
        return "my_chat_member"
    if getattr(update, "chat_member", None) is not None:
        return "chat_member"
    return "other"


def _safe_command_summary(text: str) -> str | None:
    if not text or not text.startswith("/"):
        return None
    head, *rest = text.split(maxsplit=1)
    cmd = head.split("@", 1)[0]
    if cmd == "/start" and rest:
        payload = rest[0].strip()
        if payload.startswith("cfg_"):
            return "cmd=/start payload=cfg"
        if payload.startswith("ver_"):
            return "cmd=/start payload=ver"
        return "cmd=/start payload=other"
    return f"cmd={cmd}"


def _log_update_summary(update: Update) -> None:
    try:
        kind = _update_kind(update)
        if kind in ("message", "edited_message"):
            msg = update.message or update.edited_message
            chat = getattr(msg, "chat", None)
            chat_id = getattr(chat, "id", None)
            chat_type = getattr(chat, "type", None)
            from_user = getattr(msg, "from_user", None)
            from_id = getattr(from_user, "id", None)

            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            cmd_summary = _safe_command_summary(text)

            # Avoid logging raw user text; log commands everywhere, and non-command only for private.
            if cmd_summary:
                logger.info(
                    "tg_update=%s kind=%s chat=%s(%s) from=%s %s",
                    update.update_id,
                    kind,
                    chat_id,
                    chat_type,
                    from_id,
                    cmd_summary,
                )
                return

            if chat_type == "private":
                logger.info(
                    "tg_update=%s kind=%s chat=%s(private) from=%s text_len=%s",
                    update.update_id,
                    kind,
                    chat_id,
                    from_id,
                    len(text),
                )
                return

            return

        logger.info("tg_update=%s kind=%s", update.update_id, kind)
    except Exception:
        return


def _get_admin_token_from_request(request: Request) -> str | None:
    # Prefer Authorization: Bearer <token>, fallback to X-Admin-Token or ?token=
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        parts = auth.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    token = request.headers.get("x-admin-token") or request.headers.get("X-Admin-Token")
    if token:
        return token.strip()
    token = request.query_params.get("token")
    return token.strip() if token else None


def _is_admin_request(request: Request) -> bool:
    expected = (getattr(config, "admin_api_token", "") or os.getenv("ADMIN_API_TOKEN", "")).strip()
    if not expected:
        return False
    provided = _get_admin_token_from_request(request)
    return bool(provided) and provided == expected


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

        # Debug visibility: record that we received an update (without logging message contents).
        _log_update_summary(update)
        
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
    session_id: str | None = None,
    app_name: str | None = None,
    app_domain: str | None = None,
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
async def health_check(request: Request):
    """
    Health check endpoint.
    
    Returns the health status of the bot and its components.
    """
    try:
        running = bool(telegram_bot and telegram_bot.is_running())
        payload = {"status": "ok", "running": running, "version": "2.0.0"}
        if not running:
            payload["detail"] = "initializing"

        # Only include internal details if an admin token is configured + provided.
        if _is_admin_request(request) and telegram_bot and telegram_bot.get_container():
            from database.db import db

            payload["database_ok"] = await db.health_check()
        return payload
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


@app.get("/status")
async def status(request: Request):
    """
    Status endpoint with detailed information.
    
    Returns statistics and configuration details.
    """
    try:
        if not _is_admin_request(request):
            return Response(status_code=403)

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
        return {"status": "error", "error": str(e)}


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
