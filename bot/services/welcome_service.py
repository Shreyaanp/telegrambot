"""Welcome service - manage welcome and goodbye messages."""
import logging
from typing import Optional
from sqlalchemy import select

from database.db import db
from database.models import Group

logger = logging.getLogger(__name__)


class WelcomeService:
    """
    Welcome/Goodbye message service.
    
    Manages custom welcome and goodbye messages for groups.
    Supports variables: {name}, {mention}, {group}, {count}
    """
    
    async def set_welcome(
        self,
        group_id: int,
        message: str,
        enabled: bool = True,
        destination: str = "group"
    ) -> bool:
        """
        Set welcome message for a group.
        
        Args:
            group_id: Group ID
            message: Welcome message text
            enabled: Whether welcome is enabled
            destination: Where to send welcome (group|dm|both)
            
        Returns:
            True if successful
        """
        # Validate destination
        if destination not in ["group", "dm", "both"]:
            destination = "group"
            
        async with db.session() as session:
            result = await session.execute(
                select(Group).where(Group.group_id == group_id)
            )
            group = result.scalar_one_or_none()
            
            if not group:
                # Create group settings
                group = Group(
                    group_id=group_id,
                    welcome_enabled=enabled,
                    welcome_message=message,
                    welcome_destination=destination
                )
                session.add(group)
            else:
                group.welcome_enabled = enabled
                group.welcome_message = message
                group.welcome_destination = destination
            
            await session.commit()
            logger.info(f"Welcome message set for group {group_id}, destination: {destination}")
            return True
    
    async def set_goodbye(
        self,
        group_id: int,
        message: str,
        enabled: bool = True
    ) -> bool:
        """
        Set goodbye message for a group.
        
        Args:
            group_id: Group ID
            message: Goodbye message text
            enabled: Whether goodbye is enabled
            
        Returns:
            True if successful
        """
        async with db.session() as session:
            result = await session.execute(
                select(Group).where(Group.group_id == group_id)
            )
            group = result.scalar_one_or_none()
            
            if not group:
                group = Group(
                    group_id=group_id,
                    goodbye_enabled=enabled,
                    goodbye_message=message
                )
                session.add(group)
            else:
                group.goodbye_enabled = enabled
                group.goodbye_message=message
            
            await session.commit()
            logger.info(f"Goodbye message set for group {group_id}")
            return True
    
    async def get_welcome(self, group_id: int) -> Optional[tuple[bool, str, str]]:
        """
        Get welcome message for a group.
        
        Args:
            group_id: Group ID
            
        Returns:
            Tuple of (enabled, message, destination) or None
        """
        async with db.session() as session:
            result = await session.execute(
                select(Group).where(Group.group_id == group_id)
            )
            group = result.scalar_one_or_none()
            
            if group and group.welcome_message:
                destination = getattr(group, 'welcome_destination', 'group') or 'group'
                return (group.welcome_enabled, group.welcome_message, destination)
            return None
    
    async def get_goodbye(self, group_id: int) -> Optional[tuple[bool, str]]:
        """
        Get goodbye message for a group.
        
        Args:
            group_id: Group ID
            
        Returns:
            Tuple of (enabled, message) or None
        """
        async with db.session() as session:
            result = await session.execute(
                select(Group).where(Group.group_id == group_id)
            )
            group = result.scalar_one_or_none()
            
            if group and group.goodbye_message:
                return (group.goodbye_enabled, group.goodbye_message)
            return None
    
    def format_message(
        self,
        template: str,
        user_name: str,
        user_mention: str,
        group_name: str,
        member_count: int
    ) -> str:
        """
        Format a message template with variables.
        
        Args:
            template: Message template
            user_name: User's name
            user_mention: User mention
            group_name: Group name
            member_count: Group member count
            
        Returns:
            Formatted message
        """
        return template.format(
            name=user_name,
            mention=user_mention,
            group=group_name,
            count=member_count
        )

