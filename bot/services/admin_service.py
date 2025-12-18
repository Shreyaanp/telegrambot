"""Admin service - handle kick, ban, mute, warn with great UX."""
import logging
from datetime import datetime, timedelta
from typing import Optional
from aiogram import Bot
from aiogram.types import ChatPermissions
from html import escape
from sqlalchemy import select, func, and_

from database.db import db
from database.models import Warning, AdminLog, Group

logger = logging.getLogger(__name__)


class AdminService:
    """
    Admin moderation service.
    
    Handles all admin actions with:
    - Clear logging
    - Automatic action tracking
    - User-friendly responses
    - Integration with warn system
    """
    
    async def kick_user(
        self,
        bot: Bot,
        group_id: int,
        user_id: int,
        admin_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """
        Kick a user from the group.
        
        Args:
            bot: Bot instance
            group_id: Group ID
            user_id: User to kick
            admin_id: Admin performing the action
            reason: Optional reason
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Kick the user (ban then unban)
            await bot.ban_chat_member(chat_id=group_id, user_id=user_id)
            await bot.unban_chat_member(chat_id=group_id, user_id=user_id)
            
            # Log the action
            await self._log_action(
                group_id=group_id,
                admin_id=admin_id,
                target_id=user_id,
                action="kick",
                reason=reason
            )
            await self._maybe_send_log(
                bot,
                group_id,
                admin_id=admin_id,
                target_id=user_id,
                action="kick",
                reason=reason,
            )
            
            logger.info(f"User {user_id} kicked from group {group_id} by admin {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to kick user {user_id}: {e}")
            return False
    
    async def ban_user(
        self,
        bot: Bot,
        group_id: int,
        user_id: int,
        admin_id: int,
        reason: Optional[str] = None,
        until_date: Optional[datetime] = None
    ) -> bool:
        """
        Ban a user from the group.
        
        Args:
            bot: Bot instance
            group_id: Group ID
            user_id: User to ban
            admin_id: Admin performing the action
            reason: Optional reason
            until_date: Optional unban date (None = permanent)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ban the user
            await bot.ban_chat_member(
                chat_id=group_id,
                user_id=user_id,
                until_date=until_date
            )
            
            # Log the action
            action_type = "tempban" if until_date else "ban"
            await self._log_action(
                group_id=group_id,
                admin_id=admin_id,
                target_id=user_id,
                action=action_type,
                reason=reason
            )
            await self._maybe_send_log(
                bot,
                group_id,
                admin_id=admin_id,
                target_id=user_id,
                action=action_type,
                reason=reason,
            )
            
            logger.info(f"User {user_id} banned from group {group_id} by admin {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to ban user {user_id}: {e}")
            return False
    
    async def unban_user(
        self,
        bot: Bot,
        group_id: int,
        user_id: int,
        admin_id: int
    ) -> bool:
        """
        Unban a user from the group.
        
        Args:
            bot: Bot instance
            group_id: Group ID
            user_id: User to unban
            admin_id: Admin performing the action
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Unban the user
            await bot.unban_chat_member(chat_id=group_id, user_id=user_id, only_if_banned=True)
            
            # Log the action
            await self._log_action(
                group_id=group_id,
                admin_id=admin_id,
                target_id=user_id,
                action="unban",
                reason=None
            )
            await self._maybe_send_log(
                bot,
                group_id,
                admin_id=admin_id,
                target_id=user_id,
                action="unban",
                reason=None,
            )
            
            logger.info(f"User {user_id} unbanned from group {group_id} by admin {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unban user {user_id}: {e}")
            return False
    
    async def mute_user(
        self,
        bot: Bot,
        group_id: int,
        user_id: int,
        admin_id: int,
        duration: Optional[int] = None,  # seconds
        reason: Optional[str] = None
    ) -> bool:
        """
        Mute a user in the group.
        
        Args:
            bot: Bot instance
            group_id: Group ID
            user_id: User to mute
            admin_id: Admin performing the action
            duration: Optional duration in seconds (None = permanent)
            reason: Optional reason
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Calculate until_date if duration provided
            until_date = None
            if duration:
                until_date = datetime.utcnow() + timedelta(seconds=duration)
            
            # Mute the user
            await bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            
            # Log the action
            action_type = "tempmute" if duration else "mute"
            await self._log_action(
                group_id=group_id,
                admin_id=admin_id,
                target_id=user_id,
                action=action_type,
                reason=reason
            )
            await self._maybe_send_log(
                bot,
                group_id,
                admin_id=admin_id,
                target_id=user_id,
                action=action_type,
                reason=reason,
            )
            
            logger.info(f"User {user_id} muted in group {group_id} by admin {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mute user {user_id}: {e}")
            return False
    
    async def unmute_user(
        self,
        bot: Bot,
        group_id: int,
        user_id: int,
        admin_id: int
    ) -> bool:
        """
        Unmute a user in the group.
        
        Args:
            bot: Bot instance
            group_id: Group ID
            user_id: User to unmute
            admin_id: Admin performing the action
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Unmute the user (restore all permissions)
            await bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_change_info=False,
                    can_invite_users=True,
                    can_pin_messages=False
                )
            )
            
            # Log the action
            await self._log_action(
                group_id=group_id,
                admin_id=admin_id,
                target_id=user_id,
                action="unmute",
                reason=None
            )
            await self._maybe_send_log(
                bot,
                group_id,
                admin_id=admin_id,
                target_id=user_id,
                action="unmute",
                reason=None,
            )
            
            logger.info(f"User {user_id} unmuted in group {group_id} by admin {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unmute user {user_id}: {e}")
            return False
    
    async def warn_user(
        self,
        *,
        bot: Optional[Bot] = None,
        group_id: int,
        user_id: int,
        admin_id: int,
        reason: Optional[str] = None,
    ) -> tuple[int, int]:
        """
        Warn a user in the group.
        
        Args:
            group_id: Group ID
            user_id: User to warn
            admin_id: Admin performing the action
            reason: Optional reason
            
        Returns:
            Tuple of (current_warns, warn_limit)
        """
        async with db.session() as session:
            # Add warning
            warning = Warning(
                group_id=group_id,
                telegram_id=user_id,
                warned_by=admin_id,
                reason=reason,
                warned_at=datetime.utcnow()
            )
            session.add(warning)
            await session.commit()
            
            # Get total warnings
            result = await session.execute(
                select(func.count(Warning.id))
                .where(
                    and_(
                        Warning.group_id == group_id,
                        Warning.telegram_id == user_id
                    )
                )
            )
            warn_count = result.scalar()
            
            # Get warn limit
            group_result = await session.execute(
                select(Group.warn_limit).where(Group.group_id == group_id)
            )
            group = group_result.scalar_one_or_none()
            warn_limit = group if group else 3
            
            # Log the action
            await self._log_action(
                group_id=group_id,
                admin_id=admin_id,
                target_id=user_id,
                action="warn",
                reason=reason
            )
            if bot:
                await self._maybe_send_log(
                    bot,
                    group_id,
                    admin_id=admin_id,
                    target_id=user_id,
                    action="warn",
                    reason=reason,
                )
            
            logger.info(f"User {user_id} warned in group {group_id} ({warn_count}/{warn_limit})")
            return warn_count, warn_limit
    
    async def get_warnings(self, group_id: int, user_id: int) -> list[Warning]:
        """
        Get all warnings for a user in a group.
        
        Args:
            group_id: Group ID
            user_id: User ID
            
        Returns:
            List of Warning objects
        """
        async with db.session() as session:
            result = await session.execute(
                select(Warning)
                .where(
                    and_(
                        Warning.group_id == group_id,
                        Warning.telegram_id == user_id
                    )
                )
                .order_by(Warning.warned_at.desc())
            )
            return list(result.scalars().all())
    
    async def reset_warnings(
        self,
        group_id: int,
        user_id: int,
        admin_id: int
    ) -> int:
        """
        Reset all warnings for a user in a group.
        
        Args:
            group_id: Group ID
            user_id: User ID
            admin_id: Admin performing the action
            
        Returns:
            Number of warnings removed
        """
        async with db.session() as session:
            # Get count first
            result = await session.execute(
                select(func.count(Warning.id))
                .where(
                    and_(
                        Warning.group_id == group_id,
                        Warning.telegram_id == user_id
                    )
                )
            )
            count = result.scalar()
            
            warnings_result = await session.execute(
                select(Warning).where(
                    and_(
                        Warning.group_id == group_id,
                        Warning.telegram_id == user_id,
                    )
                )
            )
            warnings = list(warnings_result.scalars().all())
            for warning in warnings:
                await session.delete(warning)
            
            await session.commit()
            
            # Log the action
            await self._log_action(
                group_id=group_id,
                admin_id=admin_id,
                target_id=user_id,
                action="resetwarns",
                reason=f"Removed {count} warnings"
            )
            
            logger.info(f"Reset {count} warnings for user {user_id} in group {group_id}")
            return count
    
    async def _log_action(
        self,
        group_id: int,
        admin_id: int,
        target_id: Optional[int],
        action: str,
        reason: Optional[str]
    ):
        """Log an admin action to the database."""
        async with db.session() as session:
            log = AdminLog(
                group_id=group_id,
                admin_id=admin_id,
                target_id=target_id,
                action=action,
                reason=reason,
                timestamp=datetime.utcnow()
            )
            session.add(log)
            await session.commit()

    async def _maybe_send_log(
        self,
        bot: Bot,
        group_id: int,
        *,
        admin_id: int,
        target_id: Optional[int],
        action: str,
        reason: Optional[str],
    ) -> None:
        try:
            async with db.session() as session:
                result = await session.execute(select(Group).where(Group.group_id == group_id))
                group = result.scalar_one_or_none()
                if not group or not getattr(group, "logs_enabled", False) or not getattr(group, "logs_chat_id", None):
                    return
                dest_chat_id = int(group.logs_chat_id)
                thread_id = int(group.logs_thread_id) if getattr(group, "logs_thread_id", None) else None

            reason_line = f"\nReason: {escape(reason)}" if reason else ""
            target_line = f"\nTarget: <code>{int(target_id)}</code>" if target_id is not None else ""
            text = (
                f"<b>Log</b>\n"
                f"Group: <code>{int(group_id)}</code>\n"
                f"Action: <code>{escape(action)}</code>\n"
                f"Admin: <code>{int(admin_id)}</code>"
                f"{target_line}"
                f"{reason_line}"
            )
            kwargs = {"disable_web_page_preview": True}
            if thread_id:
                kwargs["message_thread_id"] = thread_id
            await bot.send_message(chat_id=dest_chat_id, text=text, parse_mode="HTML", **kwargs)
        except Exception:
            return

    async def log_custom_action(
        self,
        bot: Bot,
        group_id: int,
        *,
        actor_id: int,
        target_id: Optional[int],
        action: str,
        reason: Optional[str],
    ) -> None:
        """
        Log an event that isn't necessarily a moderation action (e.g. user reports).

        This records the event in `admin_logs` and (if enabled) forwards it to the configured logs destination.
        """
        try:
            await self._log_action(
                group_id=group_id,
                admin_id=actor_id,
                target_id=target_id,
                action=action,
                reason=reason,
            )
        except Exception:
            pass
        try:
            await self._maybe_send_log(
                bot,
                group_id,
                admin_id=actor_id,
                target_id=target_id,
                action=action,
                reason=reason,
            )
        except Exception:
            pass
