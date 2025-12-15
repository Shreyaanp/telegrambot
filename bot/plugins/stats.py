"""Stats plugin - verification statistics."""
import logging
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ChatType

from bot.plugins.base import BasePlugin
from bot.services import UserService, GroupService, SessionService

logger = logging.getLogger(__name__)


class StatsPlugin(BasePlugin):
    """Plugin for verification statistics."""
    
    @property
    def name(self) -> str:
        return "stats"
    
    @property
    def description(self) -> str:
        return "Verification statistics and metrics"
    
    def __init__(self, bot, db, config, services):
        super().__init__(bot, db, config, services)
        self.user_service = UserService(db)
        self.group_service = GroupService(db)
        self.session_service = SessionService(db)
    
    async def on_load(self):
        """Register handlers when plugin is loaded."""
        await super().on_load()
        
        self.router.message.register(self.cmd_stats, Command("stats"))
        
        self.logger.info("Stats plugin loaded successfully")
    
    def get_commands(self):
        return [
            {"command": "/stats", "description": "Show verification statistics"},
        ]
    
    async def cmd_stats(self, message: Message):
        """Show verification statistics."""
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            # Global stats for DM
            total_users = await self.user_service.get_user_count()
            await message.answer(
                f"📊 **Global Statistics**\n\n"
                f"**Total Verified Users:** {total_users}"
            )
            return
        
        group_id = message.chat.id
        
        # Get group statistics
        members = await self.group_service.get_group_members(group_id)
        verified_count = await self.group_service.get_verified_count(group_id)
        pending_count = await self.session_service.get_pending_sessions_count()
        
        total_members = len(members)
        unverified_count = total_members - verified_count
        
        await message.answer(
            f"📊 **Group Statistics**\n\n"
            f"**Total Members:** {total_members}\n"
            f"**Verified:** {verified_count} ✅\n"
            f"**Unverified:** {unverified_count} ❌\n"
            f"**Pending Verifications:** {pending_count} ⏳"
        )

