"""Plugins package - imports all plugins and their models for database initialization."""

# Import all plugins
from bot.plugins.verification import VerificationPlugin
from bot.plugins.admin import AdminPlugin
from bot.plugins.warnings import WarningsPlugin
from bot.plugins.whitelist import WhitelistPlugin
from bot.plugins.rules import RulesPlugin
from bot.plugins.stats import StatsPlugin
from bot.plugins.antiflood import AntiFloodPlugin
from bot.plugins.greetings import GreetingsPlugin
from bot.plugins.filters import FiltersPlugin, MessageFilter
from bot.plugins.locks import LocksPlugin, MessageLock
from bot.plugins.notes import NotesPlugin, Note
from bot.plugins.admin_logs import AdminLogsPlugin, AdminLog

# Export all plugins
__all__ = [
    'VerificationPlugin',
    'AdminPlugin',
    'WarningsPlugin',
    'WhitelistPlugin',
    'RulesPlugin',
    'StatsPlugin',
    'AntiFloodPlugin',
    'GreetingsPlugin',
    'FiltersPlugin',
    'LocksPlugin',
    'NotesPlugin',
    'AdminLogsPlugin',
    # Models
    'MessageFilter',
    'MessageLock',
    'Note',
    'AdminLog',
]
