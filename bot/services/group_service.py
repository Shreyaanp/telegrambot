"""Group settings service - manage per-group configuration."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select

from database.db import db
from database.models import Group

logger = logging.getLogger(__name__)


class GroupService:
    """Manage group-level settings such as verification, welcome, and antiflood."""
    
    async def get_or_create_group(self, group_id: int) -> Group:
        """Fetch group settings, creating defaults if missing."""
        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == group_id))
            group = result.scalar_one_or_none()
            
            if not group:
                group = Group(group_id=group_id)
                session.add(group)
                await session.commit()
                await session.refresh(group)
                logger.info(f"Created default settings for group {group_id}")
            
            return group

    async def register_group(self, group_id: int, group_name: Optional[str] = None) -> Group:
        """Ensure group exists and update name."""
        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == group_id))
            group = result.scalar_one_or_none()
            if not group:
                group = Group(group_id=group_id, group_name=group_name)
                session.add(group)
            else:
                if group_name and group.group_name != group_name:
                    group.group_name = group_name
            await session.commit()
            await session.refresh(group)
            return group

    async def list_groups(self) -> list[Group]:
        """List all known groups."""
        async with db.session() as session:
            result = await session.execute(select(Group))
            return list(result.scalars().all())
    
    async def update_setting(
        self,
        group_id: int,
        *,
        verification_timeout: Optional[int] = None,
        action_on_timeout: Optional[str] = None,  # "kick" or "mute"
        require_rules_acceptance: Optional[bool] = None,
        captcha_enabled: Optional[bool] = None,
        captcha_style: Optional[str] = None,  # button|math
        captcha_max_attempts: Optional[int] = None,
        block_no_username: Optional[bool] = None,
        antiflood_limit: Optional[int] = None,
        antiflood_enabled: Optional[bool] = None,
        antiflood_mute_seconds: Optional[int] = None,
        silent_automations: Optional[bool] = None,
        raid_mode_enabled: Optional[bool] = None,
        raid_mode_minutes: Optional[int] = None,
        welcome_enabled: Optional[bool] = None,
        verification_enabled: Optional[bool] = None,
        join_gate_enabled: Optional[bool] = None,
        logs_enabled: Optional[bool] = None,
        logs_chat_id: Optional[int] = None,
        logs_thread_id: Optional[int] = None,
    ) -> Group:
        """Update one or more settings for a group."""
        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.group_id == group_id))
            group = result.scalar_one_or_none()
            
            if not group:
                group = Group(group_id=group_id)
                session.add(group)
            
            if verification_timeout is not None:
                group.verification_timeout = max(30, verification_timeout)
            if action_on_timeout is not None:
                # Group model stores kick_unverified; map kick->True, mute->False
                group.kick_unverified = (action_on_timeout == "kick")
            if require_rules_acceptance is not None:
                group.require_rules_acceptance = bool(require_rules_acceptance)
            if captcha_enabled is not None:
                group.captcha_enabled = bool(captcha_enabled)
            if captcha_style is not None:
                style = str(captcha_style or "").strip() or "button"
                if style not in ("button", "math"):
                    style = "button"
                group.captcha_style = style
            if captcha_max_attempts is not None:
                group.captcha_max_attempts = max(1, min(int(captcha_max_attempts), 10))
            if block_no_username is not None:
                group.block_no_username = bool(block_no_username)
            if antiflood_limit is not None:
                group.antiflood_limit = max(1, antiflood_limit)
                group.antiflood_enabled = True
            if antiflood_enabled is not None:
                group.antiflood_enabled = antiflood_enabled
            if antiflood_mute_seconds is not None:
                secs = int(antiflood_mute_seconds or 0)
                secs = max(30, min(secs, 24 * 60 * 60))
                group.antiflood_mute_seconds = secs
            if silent_automations is not None:
                group.silent_automations = bool(silent_automations)
            if raid_mode_enabled is not None:
                if raid_mode_enabled:
                    minutes = int(raid_mode_minutes or 15)
                    minutes = max(1, min(minutes, 7 * 24 * 60))
                    group.raid_mode_until = datetime.utcnow() + timedelta(minutes=minutes)
                else:
                    group.raid_mode_until = None
            if welcome_enabled is not None:
                group.welcome_enabled = welcome_enabled
            if verification_enabled is not None:
                group.verification_enabled = verification_enabled
            if join_gate_enabled is not None:
                group.join_gate_enabled = join_gate_enabled
            if logs_enabled is not None:
                group.logs_enabled = logs_enabled
                if not logs_enabled:
                    group.logs_chat_id = None
                    group.logs_thread_id = None
            if logs_chat_id is not None:
                group.logs_chat_id = logs_chat_id
                group.logs_enabled = True
            if logs_thread_id is not None:
                group.logs_thread_id = logs_thread_id
                group.logs_enabled = True
            
            await session.commit()
            await session.refresh(group)
            logger.info(f"Updated settings for group {group_id}")
            return group
