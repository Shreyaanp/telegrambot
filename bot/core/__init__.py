"""Bot core package - main bot and plugin management."""
from bot.core.bot import TelegramBot
from bot.core.plugin_manager import PluginManager

__all__ = ["TelegramBot", "PluginManager"]

