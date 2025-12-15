"""Plugin manager for loading and managing bot plugins."""
import logging
from typing import Dict, List, Type, Optional
from aiogram import Bot, Dispatcher
from bot.plugins.base import BasePlugin
from database import Database

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Manages bot plugins - loading, unloading, and lifecycle.
    
    Plugins are loaded dynamically and can be enabled/disabled without restarting the bot.
    """
    
    def __init__(self, bot: Bot, dispatcher: Dispatcher, db: Database, config):
        """
        Initialize the plugin manager.
        
        Args:
            bot: The aiogram Bot instance
            dispatcher: The aiogram Dispatcher instance
            db: Database instance
            config: Bot configuration object
        """
        self.bot = bot
        self.dispatcher = dispatcher
        self.db = db
        self.config = config
        self.plugins: Dict[str, BasePlugin] = {}
        self.services: Dict[str, any] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_service(self, name: str, service: any):
        """
        Register a service that plugins can use.
        
        Args:
            name: Service name
            service: Service instance
        """
        self.services[name] = service
        self.logger.info(f"Registered service: {name}")
    
    def get_service(self, name: str) -> Optional[any]:
        """
        Get a registered service.
        
        Args:
            name: Service name
        
        Returns:
            Service instance or None if not found
        """
        return self.services.get(name)
    
    async def load_plugin(self, plugin_class: Type[BasePlugin]) -> bool:
        """
        Load a plugin.
        
        Args:
            plugin_class: The plugin class to instantiate
        
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            # Instantiate plugin
            plugin = plugin_class(
                bot=self.bot,
                db=self.db,
                config=self.config,
                services=self.services
            )
            
            plugin_name = plugin.name
            
            # Check if already loaded
            if plugin_name in self.plugins:
                self.logger.warning(f"Plugin already loaded: {plugin_name}")
                return False
            
            # Call plugin's on_load
            await plugin.on_load()
            
            # Register plugin's router with dispatcher
            self.dispatcher.include_router(plugin.get_router())
            
            # Store plugin
            self.plugins[plugin_name] = plugin
            
            self.logger.info(
                f"✅ Loaded plugin: {plugin_name} v{plugin.version} - {plugin.description}"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load plugin {plugin_class.__name__}: {e}", exc_info=True)
            return False
    
    async def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload a plugin.
        
        Args:
            plugin_name: Name of the plugin to unload
        
        Returns:
            True if unloaded successfully, False otherwise
        """
        try:
            if plugin_name not in self.plugins:
                self.logger.warning(f"Plugin not found: {plugin_name}")
                return False
            
            plugin = self.plugins[plugin_name]
            
            # Call plugin's on_unload
            await plugin.on_unload()
            
            # Remove plugin
            del self.plugins[plugin_name]
            
            self.logger.info(f"✅ Unloaded plugin: {plugin_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to unload plugin {plugin_name}: {e}", exc_info=True)
            return False
    
    async def load_all_plugins(self, plugin_classes: List[Type[BasePlugin]]):
        """
        Load multiple plugins.
        
        Args:
            plugin_classes: List of plugin classes to load
        """
        self.logger.info(f"Loading {len(plugin_classes)} plugins...")
        
        loaded_count = 0
        for plugin_class in plugin_classes:
            if await self.load_plugin(plugin_class):
                loaded_count += 1
        
        self.logger.info(f"✅ Loaded {loaded_count}/{len(plugin_classes)} plugins")
    
    async def unload_all_plugins(self):
        """Unload all plugins."""
        plugin_names = list(self.plugins.keys())
        self.logger.info(f"Unloading {len(plugin_names)} plugins...")
        
        for plugin_name in plugin_names:
            await self.unload_plugin(plugin_name)
        
        self.logger.info("✅ All plugins unloaded")
    
    def get_plugin(self, plugin_name: str) -> Optional[BasePlugin]:
        """
        Get a loaded plugin by name.
        
        Args:
            plugin_name: Plugin name
        
        Returns:
            Plugin instance or None if not found
        """
        return self.plugins.get(plugin_name)
    
    def get_all_plugins(self) -> List[BasePlugin]:
        """
        Get all loaded plugins.
        
        Returns:
            List of loaded plugin instances
        """
        return list(self.plugins.values())
    
    def get_all_commands(self) -> List[Dict[str, str]]:
        """
        Get all commands from all loaded plugins.
        
        Returns:
            List of command dicts from all plugins
        """
        commands = []
        for plugin in self.plugins.values():
            commands.extend(plugin.get_commands())
        return commands
    
    async def health_check(self) -> Dict[str, bool]:
        """
        Run health check on all plugins.
        
        Returns:
            Dict mapping plugin names to health status
        """
        results = {}
        for plugin_name, plugin in self.plugins.items():
            try:
                results[plugin_name] = await plugin.health_check()
            except Exception as e:
                self.logger.error(f"Health check failed for {plugin_name}: {e}")
                results[plugin_name] = False
        return results
    
    def get_status(self) -> Dict[str, any]:
        """
        Get plugin manager status.
        
        Returns:
            Dict with plugin manager status info
        """
        return {
            "total_plugins": len(self.plugins),
            "loaded_plugins": [
                {
                    "name": p.name,
                    "version": p.version,
                    "description": p.description
                }
                for p in self.plugins.values()
            ],
            "total_services": len(self.services),
            "services": list(self.services.keys())
        }

