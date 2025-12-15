"""Admin logs plugin for tracking admin actions."""
import logging
from datetime import datetime, timedelta
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from bot.plugins.base import BasePlugin
from bot.services.permission_service import PermissionService
from database.db import get_session
from database.models import Base
from sqlalchemy import Column, Integer, String, Text, DateTime


class AdminLog(Base):
    """Admin logs table."""
    __tablename__ = "admin_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False, index=True)
    admin_id = Column(Integer, nullable=False)
    action = Column(String, nullable=False)  # kick, ban, warn, verify, etc.
    target_user_id = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class AdminLogsPlugin(BasePlugin):
    """Plugin for tracking and viewing admin actions."""
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.permission_service = PermissionService()
    
    def get_name(self) -> str:
        return "Admin Logs"
    
    def get_description(self) -> str:
        return "Track and view admin actions"
    
    def get_commands(self) -> list:
        return [
            ("adminlog", "View admin action logs"),
        ]
    
    def register_handlers(self, router: Router):
        """Register all handlers for this plugin."""
        router.message.register(self.cmd_adminlog, Command("adminlog"))
    
    # Commands
    
    async def cmd_adminlog(self, message: Message):
        """View admin action logs."""
        # Check if in group
        if message.chat.type not in ["group", "supergroup"]:
            await message.answer("❌ This command can only be used in groups.")
            return
        
        # Check if user is admin
        is_admin = await self.permission_service.is_admin(message.chat.id, message.from_user.id)
        if not is_admin:
            from bot.utils.messages import permission_denied_message
            await message.answer(permission_denied_message())
            return
        
        # Parse arguments
        args = message.text.split()
        target_user_id = None
        
        if len(args) > 1:
            # Check if argument is a user mention or ID
            arg = args[1]
            if arg.startswith("@"):
                # Try to get user ID from mention (not fully implemented)
                pass
            elif arg.isdigit():
                target_user_id = int(arg)
        
        # Get logs from database
        async with get_session() as session:
            from sqlalchemy import select
            
            stmt = select(AdminLog).where(
                AdminLog.group_id == message.chat.id
            )
            
            if target_user_id:
                stmt = stmt.where(AdminLog.target_user_id == target_user_id)
            
            stmt = stmt.order_by(AdminLog.timestamp.desc()).limit(20)
            
            result = await session.execute(stmt)
            logs = result.scalars().all()
        
        if not logs:
            await message.answer(
                "📋 **No Admin Actions Logged**\n\n"
                "Admin actions will appear here once they occur."
            )
            return
        
        # Build log message
        log_lines = []
        action_emoji = {
            "kick": "🚪",
            "ban": "🚫",
            "warn": "⚠️",
            "verify": "✅",
            "mute": "🔇",
            "unmute": "🔊",
            "whitelist_add": "➕",
            "whitelist_remove": "➖"
        }
        
        for log in logs:
            emoji = action_emoji.get(log.action, "📝")
            time_ago = self._time_ago(log.timestamp)
            
            target_text = f"user {log.target_user_id}" if log.target_user_id else "N/A"
            reason_text = f"\n   Reason: {log.reason}" if log.reason else ""
            
            log_lines.append(
                f"{emoji} **{log.action.capitalize()}** → {target_text}\n"
                f"   By: {log.admin_id} • {time_ago}{reason_text}"
            )
        
        log_text = "\n\n".join(log_lines)
        
        await message.answer(
            f"📋 **Admin Action Log** (Last 20)\n\n{log_text}"
        )
    
    # Helper Methods
    
    @staticmethod
    async def log_action(
        group_id: int,
        admin_id: int,
        action: str,
        target_user_id: int = None,
        reason: str = None
    ):
        """Log an admin action to the database."""
        async with get_session() as session:
            log_entry = AdminLog(
                group_id=group_id,
                admin_id=admin_id,
                action=action,
                target_user_id=target_user_id,
                reason=reason
            )
            session.add(log_entry)
            await session.commit()
    
    def _time_ago(self, timestamp: datetime) -> str:
        """Convert timestamp to human-readable time ago."""
        now = datetime.utcnow()
        diff = now - timestamp
        
        if diff < timedelta(minutes=1):
            return "just now"
        elif diff < timedelta(hours=1):
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes}m ago"
        elif diff < timedelta(days=1):
            hours = int(diff.total_seconds() / 3600)
            return f"{hours}h ago"
        elif diff < timedelta(days=7):
            days = diff.days
            return f"{days}d ago"
        else:
            return timestamp.strftime("%Y-%m-%d")

