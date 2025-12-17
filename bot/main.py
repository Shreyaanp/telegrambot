"""Main bot entry point - unified for both polling and webhook modes."""
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from bot.config import Config
from bot.container import ServiceContainer
from bot.handlers.commands import create_command_handlers
from bot.handlers.member_events import create_member_handlers, create_admin_join_handlers
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
        self.started_at: float | None = None
    
    async def initialize(self):
        """Initialize all bot components."""
        logger.info("=" * 70)
        logger.info("🤖 TELEGRAM VERIFICATION BOT - INITIALIZING")
        logger.info("=" * 70)
        
        try:
            # Initialize database
            logger.info("📊 Initializing database...")
            await db.create_tables()
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
            admin_router = create_admin_handlers(self.container)
            content_router = create_content_handlers(self.container)
            message_router = create_message_handlers(self.container)
            rbac_router = create_rbac_help_handlers(self.container)
            
            self.dispatcher.include_router(command_router)
            self.dispatcher.include_router(admin_router)
            self.dispatcher.include_router(content_router)
            self.dispatcher.include_router(member_router)
            self.dispatcher.include_router(admin_join_router)
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
                    BotCommand(command="verify", description="Verify with Mercle"),
                ],
                scope=BotCommandScopeAllPrivateChats(),
            )

            # Keep group commands minimal for normal users.
            await self.bot.set_my_commands(
                commands=[
                    BotCommand(command="menu", description="Open settings in DM (admins)"),
                    BotCommand(command="actions", description="Moderate (reply-first)"),
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
