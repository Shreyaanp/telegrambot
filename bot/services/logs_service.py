"""Logs service - query admin action logs."""
import logging
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, and_

from database.db import db
from database.models import AdminLog

logger = logging.getLogger(__name__)


class LogsService:
    """
    Admin logs service.
    
    Query and retrieve admin action logs.
    """
    
    async def get_recent_logs(
        self,
        group_id: int,
        limit: int = 10
    ) -> List[AdminLog]:
        """
        Get recent admin logs for a group.
        
        Args:
            group_id: Group ID
            limit: Number of logs to return
            
        Returns:
            List of AdminLog objects
        """
        async with db.session() as session:
            result = await session.execute(
                select(AdminLog)
                .where(AdminLog.group_id == group_id)
                .order_by(AdminLog.timestamp.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
    
    async def get_logs_by_admin(
        self,
        group_id: int,
        admin_id: int,
        limit: int = 10
    ) -> List[AdminLog]:
        """
        Get logs for a specific admin.
        
        Args:
            group_id: Group ID
            admin_id: Admin's Telegram ID
            limit: Number of logs to return
            
        Returns:
            List of AdminLog objects
        """
        async with db.session() as session:
            result = await session.execute(
                select(AdminLog)
                .where(
                    and_(
                        AdminLog.group_id == group_id,
                        AdminLog.admin_id == admin_id
                    )
                )
                .order_by(AdminLog.timestamp.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
    
    async def get_logs_by_target(
        self,
        group_id: int,
        target_id: int,
        limit: int = 10
    ) -> List[AdminLog]:
        """
        Get logs for a specific target user.
        
        Args:
            group_id: Group ID
            target_id: Target user's Telegram ID
            limit: Number of logs to return
            
        Returns:
            List of AdminLog objects
        """
        async with db.session() as session:
            result = await session.execute(
                select(AdminLog)
                .where(
                    and_(
                        AdminLog.group_id == group_id,
                        AdminLog.target_id == target_id
                    )
                )
                .order_by(AdminLog.timestamp.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
    
    async def get_logs_by_action(
        self,
        group_id: int,
        action: str,
        limit: int = 10
    ) -> List[AdminLog]:
        """
        Get logs for a specific action type.
        
        Args:
            group_id: Group ID
            action: Action type (kick, ban, warn, etc.)
            limit: Number of logs to return
            
        Returns:
            List of AdminLog objects
        """
        async with db.session() as session:
            result = await session.execute(
                select(AdminLog)
                .where(
                    and_(
                        AdminLog.group_id == group_id,
                        AdminLog.action == action
                    )
                )
                .order_by(AdminLog.timestamp.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
    
    async def get_logs_in_timeframe(
        self,
        group_id: int,
        hours: int = 24
    ) -> List[AdminLog]:
        """
        Get logs from the last N hours.
        
        Args:
            group_id: Group ID
            hours: Number of hours to look back
            
        Returns:
            List of AdminLog objects
        """
        async with db.session() as session:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            
            result = await session.execute(
                select(AdminLog)
                .where(
                    and_(
                        AdminLog.group_id == group_id,
                        AdminLog.timestamp >= cutoff
                    )
                )
                .order_by(AdminLog.timestamp.desc())
            )
            return list(result.scalars().all())

