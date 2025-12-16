"""Filter service - message filtering and auto-responses."""
import logging
from typing import Optional, List
from sqlalchemy import select, and_, delete

from database.db import db
from database.models import Filter

logger = logging.getLogger(__name__)


class FilterService:
    """
    Message filter service.
    
    Auto-respond or delete messages based on keywords.
    """
    
    async def add_filter(
        self,
        group_id: int,
        keyword: str,
        response: str,
        admin_id: int,
        filter_type: str = "text"
    ) -> bool:
        """
        Add a message filter.
        
        Args:
            group_id: Group ID
            keyword: Trigger keyword
            response: Response text
            admin_id: Admin adding the filter
            filter_type: Filter type (text, delete, warn)
            
        Returns:
            True if successful
        """
        async with db.session() as session:
            # Check if filter exists
            result = await session.execute(
                select(Filter)
                .where(
                    and_(
                        Filter.group_id == group_id,
                        Filter.keyword == keyword.lower()
                    )
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing filter
                existing.response = response
                existing.filter_type = filter_type
            else:
                # Create new filter
                filter_obj = Filter(
                    group_id=group_id,
                    keyword=keyword.lower(),
                    response=response,
                    filter_type=filter_type,
                    created_by=admin_id
                )
                session.add(filter_obj)
            
            await session.commit()
            logger.info(f"Filter '{keyword}' added to group {group_id}")
            return True
    
    async def remove_filter(self, group_id: int, keyword: str) -> bool:
        """
        Remove a filter.
        
        Args:
            group_id: Group ID
            keyword: Trigger keyword
            
        Returns:
            True if removed, False if not found
        """
        async with db.session() as session:
            result = await session.execute(
                delete(Filter)
                .where(
                    and_(
                        Filter.group_id == group_id,
                        Filter.keyword == keyword.lower()
                    )
                )
            )
            await session.commit()
            
            removed = result.rowcount > 0
            if removed:
                logger.info(f"Filter '{keyword}' removed from group {group_id}")
            return removed
    
    async def check_filters(self, group_id: int, message_text: str) -> Optional[Filter]:
        """
        Check if message matches any filters.
        
        Args:
            group_id: Group ID
            message_text: Message text to check
            
        Returns:
            Matching Filter object or None
        """
        async with db.session() as session:
            result = await session.execute(
                select(Filter).where(Filter.group_id == group_id)
            )
            filters = result.scalars().all()
            
            message_lower = message_text.lower()
            for filter_obj in filters:
                if filter_obj.keyword in message_lower:
                    return filter_obj
            
            return None
    
    async def list_filters(self, group_id: int) -> List[Filter]:
        """
        List all filters in a group.
        
        Args:
            group_id: Group ID
            
        Returns:
            List of Filter objects
        """
        async with db.session() as session:
            result = await session.execute(
                select(Filter)
                .where(Filter.group_id == group_id)
                .order_by(Filter.keyword)
            )
            return list(result.scalars().all())

