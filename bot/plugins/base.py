"""Base plugin interface for the bot plugin system."""
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from aiogram import Bot, Router
from database import Database

logger = logging.getLogger(__name__)


class BasePlugin(ABC):
    """
    Base class for all bot plugins.
    
    Plugins are self-contained modules that handle specific bot features.
    Each plugin registers its own handlers and has access to bot, database, and services.
    """
    
    def __init__(
        self,
        bot: Bot,
        db: Database,
        config: Any,
        services: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the plugin.
        
        Args:
            bot: The aiogram Bot instance
            db: Database instance
            config: Bot configuration object
            services: Dictionary of available services (mercle_sdk, etc.)
        """
        self.bot = bot
        self.db = db
        self.config = config
        self.services = services or {}
        self.router = Router()  # Each plugin has its own router
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name."""
        pass
    
    @property
    def description(self) -> str:
        """Plugin description."""
        return "No description provided"
    
    @property
    def version(self) -> str:
        """Plugin version."""
        return "1.0.0"
    
    async def on_load(self):
        """
        Called when plugin is loaded.
        
        Register handlers, setup tasks, etc.
        Must be implemented by subclasses.
        """
        self.logger.info(f"Loading plugin: {self.name} v{self.version}")
    
    async def on_unload(self):
        """
        Called when plugin is unloaded.
        
        Cleanup resources, cancel tasks, etc.
        """
        self.logger.info(f"Unloading plugin: {self.name}")
    
    def get_commands(self) -> List[Dict[str, str]]:
        """
        Get list of commands provided by this plugin.
        
        Returns:
            List of dicts with 'command' and 'description' keys
            Example: [{"command": "/verify", "description": "Start verification"}]
        """
        return []
    
    def get_router(self) -> Router:
        """
        Get the plugin's router for handler registration.
        
        Returns:
            The plugin's Router instance
        """
        return self.router
    
    async def health_check(self) -> bool:
        """
        Health check for the plugin.
        
        Returns:
            True if plugin is healthy, False otherwise
        """
        return True
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(name={self.name}, version={self.version})>"

