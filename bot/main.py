"""Main bot entry point - unified for both polling and webhook modes."""
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    MenuButtonWebApp,
    WebAppInfo,
)

from bot.config import Config
from bot.container import ServiceContainer
from bot.handlers.commands import create_command_handlers
from bot.handlers.member_events import create_member_handlers, create_admin_join_handlers, create_leave_handlers
from bot.handlers.join_requests import create_join_request_handlers
from bot.handlers.admin_commands import create_admin_handlers
from bot.handlers.content_commands import create_content_handlers
from bot.handlers.message_handlers import create_message_handlers
from bot.handlers.rbac_help import create_rbac_help_handlers
from database.db import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log")
    ]
)
logger = logging.getLogger(__name__)


class TelegramBot:
    """
    Main bot class - clean architecture with dependency injection.
    
    This replaces the messy old architecture with a simple, maintainable design.
    """
    
    def __init__(self, config: Config):
        """Initialize the bot."""
        self.config = config
        self.bot: Bot = None
        self.dispatcher: Dispatcher = None
        self.container: ServiceContainer = None
        self._running = False
        self._cleanup_task: asyncio.Task | None = None
        self._jobs_task: asyncio.Task | None = None
        self.started_at: float | None = None
    
    async def initialize(self):
        """Initialize all bot components."""
        logger.info("=" * 70)
        logger.info("🤖 TELEGRAM VERIFICATION BOT - INITIALIZING")
        logger.info("=" * 70)
        
        try:
            # Initialize database
            logger.info("📊 Initializing database...")
            await db.connect()
            await db.require_schema()
            logger.info("✅ Database initialized")
            
            # Initialize service container
            logger.info("🔧 Initializing services...")
            self.container = await ServiceContainer.create(self.config)
            logger.info("✅ Services initialized")
            
            # Initialize bot
            logger.info("🤖 Initializing bot...")
            self.bot = Bot(
                token=self.config.bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
            )
            logger.info("✅ Bot initialized")
            
            # Initialize dispatcher
            logger.info("📡 Initializing dispatcher...")
            self.dispatcher = Dispatcher()
            logger.info("✅ Dispatcher initialized")
            
            # Register handlers
            logger.info("📝 Registering handlers...")
            command_router = create_command_handlers(self.container)
            member_router = create_member_handlers(self.container)
            admin_join_router = create_admin_join_handlers(self.container)
            leave_router = create_leave_handlers(self.container)
            admin_router = create_admin_handlers(self.container)
            content_router = create_content_handlers(self.container)
            message_router = create_message_handlers(self.container)
            rbac_router = create_rbac_help_handlers(self.container)
            join_req_router = create_join_request_handlers(self.container)
            
            self.dispatcher.include_router(command_router)
            self.dispatcher.include_router(admin_router)
            self.dispatcher.include_router(content_router)
            self.dispatcher.include_router(member_router)
            self.dispatcher.include_router(admin_join_router)
            self.dispatcher.include_router(leave_router)
            self.dispatcher.include_router(join_req_router)
            self.dispatcher.include_router(rbac_router)
            self.dispatcher.include_router(message_router)  # Last, so it doesn't intercept commands
            logger.info("✅ All handlers registered")
            
            logger.info("=" * 70)
            logger.info("✅ BOT INITIALIZATION COMPLETE")
            logger.info("=" * 70)
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize bot: {e}", exc_info=True)
            raise
    
    async def start(self):
        """Start the bot and display info."""
        if self._running:
            logger.warning("Bot is already running")
            return
        
        logger.info("=" * 70)
        logger.info("🚀 STARTING BOT")
        logger.info("=" * 70)
        
        try:
            self._running = True
            self.started_at = asyncio.get_running_loop().time()

            # Background cleanup (polling mode + non-webhook runners)
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            self._jobs_task = asyncio.create_task(self._jobs_worker())
            
            # Get bot info
            bot_info = await self.bot.get_me()
            logger.info(f"📱 Bot username: @{bot_info.username}")
            logger.info(f"🆔 Bot ID: {bot_info.id}")
            logger.info(f"🔗 Mercle API: {self.config.mercle_api_url}")
            logger.info(f"⏱️  Verification timeout: {self.config.timeout_minutes} minutes")
            logger.info(f"⚙️  Action on timeout: {self.config.action_on_timeout}")
            logger.info(f"🌐 Mode: {'Production (webhook)' if self.config.is_production else 'Development (polling)'}")
            
            logger.info("=" * 70)
            logger.info("✅ BOT IS RUNNING")
            logger.info("=" * 70)

            # Set slash command menu (Telegram-scoped; cannot be per custom role/user)
            await self._set_command_menu()
            
        except Exception as e:
            logger.error(f"❌ Failed to start bot: {e}", exc_info=True)
            self._running = False
            raise

    async def _set_command_menu(self):
        """
        Configure Telegram's "/" command list.

        Note: Telegram supports command scopes (private/groups/admins) but not per-user custom roles.
        """
        try:
            await self.bot.set_my_commands(
                commands=[
                    BotCommand(command="start", description="Home"),
                    BotCommand(command="help", description="Help"),
                    BotCommand(command="status", description="Your verification status"),
                    BotCommand(command="verify", description="Verify with Mercle"),
                    BotCommand(command="menu", description="Settings (admins)"),
                ],
                scope=BotCommandScopeAllPrivateChats(),
            )

            # Keep group commands minimal for normal users.
            await self.bot.set_my_commands(
                commands=[
                    BotCommand(command="menu", description="Open settings in DM (admins)"),
                    BotCommand(command="actions", description="Moderate (reply-first)"),
                    BotCommand(command="report", description="Report a message (reply)"),
                    BotCommand(command="ticket", description="Contact admins (support)"),
                    BotCommand(command="checkperms", description="Check bot permissions (admins)"),
                    BotCommand(command="rules", description="Show group rules"),
                    BotCommand(command="mycommands", description="Show commands you can use"),
                ],
                scope=BotCommandScopeAllGroupChats(),
            )

            # Admin-visible list (Telegram admins only).
            await self.bot.set_my_commands(
                commands=[
                    BotCommand(command="menu", description="Open settings in DM"),
                    BotCommand(command="actions", description="Open action panel (reply)"),
                    BotCommand(command="checkperms", description="Check bot permissions"),
                    BotCommand(command="status", description="Bot status (admin)"),
                    BotCommand(command="modlog", description="View admin logs"),
                    BotCommand(command="mycommands", description="Show commands you can use"),
                    BotCommand(command="kick", description="Kick a user (reply)"),
                    BotCommand(command="ban", description="Ban a user (reply)"),
                    BotCommand(command="mute", description="Mute a user (reply)"),
                    BotCommand(command="unmute", description="Unmute a user (reply)"),
                    BotCommand(command="warn", description="Warn a user (reply)"),
                    BotCommand(command="roles", description="Manage custom roles"),
                    BotCommand(command="lock", description="Lock links/media"),
                    BotCommand(command="unlock", description="Unlock links/media"),
                ],
                scope=BotCommandScopeAllChatAdministrators(),
            )

            # Mini App menu button (global). If this fails, the Mini App can still be configured via BotFather.
            if self.config.webhook_url:
                try:
                    app_url = self.config.webhook_url.rstrip("/") + "/app"
                    await self.bot.set_chat_menu_button(
                        menu_button=MenuButtonWebApp(text="Settings", web_app=WebAppInfo(url=app_url))
                    )
                except Exception as e:
                    logger.warning(f"Failed to set menu button: {e}")
        except Exception as e:
            logger.warning(f"Failed to set command menu: {e}")

    async def _periodic_cleanup(self):
        while self._running:
            try:
                await asyncio.sleep(60)
                if self.container:
                    await self.container.user_manager.cleanup_expired_sessions()
                    expired = await self.container.pending_verification_service.find_expired()
                    if expired:
                        bot_info = await self.bot.get_me()
                        for pending in expired:
                            group = await self.container.group_service.get_or_create_group(int(pending.group_id))
                            kind = getattr(pending, "kind", "post_join")
                            if kind == "join_request":
                                try:
                                    await self.bot.decline_chat_join_request(chat_id=int(pending.group_id), user_id=int(pending.telegram_id))
                                except Exception:
                                    pass
                                await self.container.pending_verification_service.decide(int(pending.id), status="timed_out", decided_by=bot_info.id)
                                continue

                            action = "kick" if group.kick_unverified else "mute"
                            if action == "kick":
                                try:
                                    await self.bot.ban_chat_member(chat_id=int(pending.group_id), user_id=int(pending.telegram_id))
                                    await self.bot.unban_chat_member(chat_id=int(pending.group_id), user_id=int(pending.telegram_id))
                                except Exception:
                                    pass
                            await self.container.pending_verification_service.decide(int(pending.id), status="timed_out", decided_by=bot_info.id)
                            await self.container.pending_verification_service.edit_or_delete_group_prompt(self.bot, pending, "⏱ Timed out")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic cleanup error: {e}")

    async def _jobs_worker(self):
        """
        Background worker for DB-backed jobs (broadcasts, sequences, tickets).
        """
        last_reap_at: datetime | None = None
        while self._running:
            try:
                await asyncio.sleep(0)  # allow cancellation
                if not self.container:
                    await asyncio.sleep(2)
                    continue

                now = datetime.utcnow()
                if last_reap_at is None or (now - last_reap_at) > timedelta(seconds=60):
                    try:
                        await self.container.jobs_service.release_stale_locks(max_age_seconds=600)
                    except Exception:
                        pass
                    last_reap_at = now

                jobs = await self.container.jobs_service.claim_due(limit=3)
                if not jobs:
                    await asyncio.sleep(2)
                    continue

                for job in jobs:
                    try:
                        if job.job_type == "broadcast_send":
                            broadcast_id = int(job.payload.get("broadcast_id") or 0)
                            if not broadcast_id:
                                await self.container.jobs_service.mark_failed(job.id, last_error="missing broadcast_id")
                                continue

                            result = await self.container.broadcast_service.run_send_job(
                                self.bot, broadcast_id=broadcast_id, batch_size=5
                            )
                            if result.done:
                                await self.container.jobs_service.mark_done(job.id)
                            else:
                                delay = int(result.retry_after_seconds or 1)
                                delay = max(1, min(delay, 3600))
                                await self.container.jobs_service.reschedule(
                                    job.id,
                                    run_at=datetime.utcnow() + timedelta(seconds=delay),
                                    last_error=result.detail,
                                )
                            continue

                        if job.job_type == "sequence_step":
                            run_step_id = int(job.payload.get("run_step_id") or 0)
                            if not run_step_id:
                                await self.container.jobs_service.mark_failed(job.id, last_error="missing run_step_id")
                                continue

                            result = await self.container.sequence_service.run_step_job(
                                self.bot, run_step_id=run_step_id
                            )
                            if result.done:
                                await self.container.jobs_service.mark_done(job.id)
                            else:
                                delay = int(result.retry_after_seconds or 1)
                                delay = max(1, min(delay, 3600))
                                await self.container.jobs_service.reschedule(
                                    job.id,
                                    run_at=datetime.utcnow() + timedelta(seconds=delay),
                                    last_error=result.detail,
                                )
                            continue

                        await self.container.jobs_service.mark_failed(job.id, last_error=f"unknown job_type={job.job_type}")
                    except Exception as e:
                        await self.container.jobs_service.mark_failed(job.id, last_error=str(e))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Jobs worker error: {e}")
                await asyncio.sleep(2)
    
    async def stop(self):
        """Stop the bot and cleanup."""
        if not self._running:
            logger.warning("Bot is not running")
            return
        
        logger.info("=" * 70)
        logger.info("🛑 STOPPING BOT")
        logger.info("=" * 70)
        
        try:
            self._running = False

            if self._cleanup_task:
                self._cleanup_task.cancel()
                self._cleanup_task = None
            if self._jobs_task:
                self._jobs_task.cancel()
                self._jobs_task = None
            
            # Cleanup services
            if self.container:
                logger.info("🧹 Cleaning up services...")
                await self.container.cleanup()
                logger.info("✅ Services cleaned up")
            
            # Close bot session
            if self.bot:
                logger.info("🤖 Closing bot session...")
                await self.bot.session.close()
                logger.info("✅ Bot session closed")
            
            # Close database
            logger.info("📊 Closing database...")
            await db.close()
            logger.info("✅ Database closed")
            
            logger.info("=" * 70)
            logger.info("✅ BOT STOPPED")
            logger.info("=" * 70)
            
        except Exception as e:
            logger.error(f"❌ Error stopping bot: {e}", exc_info=True)
            raise
    
    async def run_polling(self):
        """Run bot in polling mode (for local development)."""
        await self.start()
        
        try:
            logger.info("📡 Starting polling...")
            await self.dispatcher.start_polling(
                self.bot,
                allowed_updates=self.dispatcher.resolve_used_update_types()
            )
        except KeyboardInterrupt:
            logger.info("⌨️  Received interrupt signal")
        except Exception as e:
            logger.error(f"❌ Polling error: {e}", exc_info=True)
        finally:
            await self.stop()
    
    def get_bot(self) -> Bot:
        """Get the bot instance."""
        return self.bot
    
    def get_dispatcher(self) -> Dispatcher:
        """Get the dispatcher instance."""
        return self.dispatcher
    
    def get_container(self) -> ServiceContainer:
        """Get the service container."""
        return self.container
    
    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._running

    def uptime_seconds(self) -> int:
        if self.started_at is None:
            return 0
        return int(asyncio.get_running_loop().time() - self.started_at)


async def main():
    """Main entry point for polling mode."""
    try:
        # Load configuration
        config = Config.from_env()
        logger.info("✅ Configuration loaded")
        
        # Create and initialize bot
        bot = TelegramBot(config)
        await bot.initialize()
        
        # Run in polling mode
        await bot.run_polling()
        
    except KeyboardInterrupt:
        logger.info("⌨️  Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⌨️  Bot stopped by user")
