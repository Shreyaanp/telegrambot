"""Main bot core - initialization and lifecycle management."""
import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from bot.core.plugin_manager import PluginManager
from database import Database, init_database, close_database
from bot.config import Config

logger = logging.getLogger(__name__)


class TelegramBot:
    """
    Main bot class - handles initialization, plugin loading, and lifecycle.
    
    This is the entry point for the bot application.
    """
    
    def __init__(self, config: Config):
        """
        Initialize the bot.
        
        Args:
            config: Bot configuration object
        """
        self.config = config
        self.bot: Bot = None
        self.dispatcher: Dispatcher = None
        self.db: Database = None
        self.plugin_manager: PluginManager = None
        self._running = False
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize bot components."""
        self.logger.info("=" * 70)
        self.logger.info("🤖 TELEGRAM VERIFICATION BOT - INITIALIZING")
        self.logger.info("=" * 70)
        
        try:
            # Initialize database
            self.logger.info("📊 Initializing database...")
            self.db = await init_database()
            self.logger.info("✅ Database initialized")
            
            # Initialize bot
            self.logger.info("🤖 Initializing bot...")
            self.bot = Bot(
                token=self.config.bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
            )
            self.logger.info("✅ Bot initialized")
            
            # Initialize dispatcher
            self.logger.info("📡 Initializing dispatcher...")
            self.dispatcher = Dispatcher()
            self.logger.info("✅ Dispatcher initialized")
            
            # Initialize plugin manager
            self.logger.info("🔌 Initializing plugin manager...")
            self.plugin_manager = PluginManager(
                bot=self.bot,
                dispatcher=self.dispatcher,
                db=self.db,
                config=self.config
            )
            self.logger.info("✅ Plugin manager initialized")
            
            self.logger.info("=" * 70)
            self.logger.info("✅ BOT INITIALIZATION COMPLETE")
            self.logger.info("=" * 70)
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize bot: {e}", exc_info=True)
            raise
    
    async def load_plugins(self, plugin_classes: list):
        """
        Load bot plugins.
        
        Args:
            plugin_classes: List of plugin classes to load
        """
        self.logger.info("🔌 Loading plugins...")
        await self.plugin_manager.load_all_plugins(plugin_classes)
        self.logger.info(f"✅ Plugins loaded: {len(self.plugin_manager.get_all_plugins())}")
    
    async def start(self):
        """Start the bot."""
        if self._running:
            self.logger.warning("Bot is already running")
            return
        
        self.logger.info("=" * 70)
        self.logger.info("🚀 STARTING BOT")
        self.logger.info("=" * 70)
        
        try:
            self._running = True
            
            # Get bot info
            bot_info = await self.bot.get_me()
            self.logger.info(f"Bot username: @{bot_info.username}")
            self.logger.info(f"Bot ID: {bot_info.id}")
            
            # Display loaded plugins
            plugins = self.plugin_manager.get_all_plugins()
            self.logger.info(f"Loaded plugins: {len(plugins)}")
            for plugin in plugins:
                self.logger.info(f"  - {plugin.name} v{plugin.version}")
            
            # Display available commands
            commands = self.plugin_manager.get_all_commands()
            self.logger.info(f"Available commands: {len(commands)}")
            for cmd in commands:
                self.logger.info(f"  - {cmd['command']}: {cmd['description']}")
            
            self.logger.info("=" * 70)
            self.logger.info("✅ BOT IS RUNNING")
            self.logger.info("=" * 70)
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start bot: {e}", exc_info=True)
            self._running = False
            raise
    
    async def stop(self):
        """Stop the bot."""
        if not self._running:
            self.logger.warning("Bot is not running")
            return
        
        self.logger.info("=" * 70)
        self.logger.info("🛑 STOPPING BOT")
        self.logger.info("=" * 70)
        
        try:
            self._running = False
            
            # Unload plugins
            self.logger.info("🔌 Unloading plugins...")
            await self.plugin_manager.unload_all_plugins()
            self.logger.info("✅ Plugins unloaded")
            
            # Close bot session
            self.logger.info("🤖 Closing bot session...")
            await self.bot.session.close()
            self.logger.info("✅ Bot session closed")
            
            # Close database
            self.logger.info("📊 Closing database...")
            await close_database()
            self.logger.info("✅ Database closed")
            
            self.logger.info("=" * 70)
            self.logger.info("✅ BOT STOPPED")
            self.logger.info("=" * 70)
            
        except Exception as e:
            self.logger.error(f"❌ Error stopping bot: {e}", exc_info=True)
            raise
    
    async def run_polling(self):
        """Run bot in polling mode (for local testing)."""
        await self.start()
        
        try:
            self.logger.info("📡 Starting polling...")
            await self.dispatcher.start_polling(self.bot, allowed_updates=self.dispatcher.resolve_used_update_types())
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        finally:
            await self.stop()
    
    def get_dispatcher(self) -> Dispatcher:
        """Get the bot's dispatcher."""
        return self.dispatcher
    
    def get_bot(self) -> Bot:
        """Get the bot instance."""
        return self.bot
    
    def get_database(self) -> Database:
        """Get the database instance."""
        return self.db
    
    def get_plugin_manager(self) -> PluginManager:
        """Get the plugin manager."""
        return self.plugin_manager
    
    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._running
    
    async def health_check(self) -> dict:
        """
        Run health check on all components.
        
        Returns:
            Dict with health status of all components
        """
        result = {
            "bot": False,
            "database": False,
            "plugins": {}
        }
        
        try:
            # Check bot
            if self.bot:
                await self.bot.get_me()
                result["bot"] = True
            
            # Check database
            if self.db:
                result["database"] = await self.db.health_check()
            
            # Check plugins
            if self.plugin_manager:
                result["plugins"] = await self.plugin_manager.health_check()
            
        except Exception as e:
            self.logger.error(f"Health check error: {e}")
        
        return result

