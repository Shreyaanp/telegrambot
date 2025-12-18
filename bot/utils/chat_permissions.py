"""ChatPermissions helpers.

Telegram user restrictions are set via ChatPermissions objects. This module provides
safe, explicit permission sets and a best-effort way to restore chat-default
permissions when unrestricting a user.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import ChatPermissions


def muted_permissions() -> ChatPermissions:
    """Deny all send-related capabilities for a non-admin member."""
    return ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_invite_users=False,
        can_change_info=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )


def full_member_permissions() -> ChatPermissions:
    """
    Best-effort "unrestricted member" permission set.

    Prefer `get_chat_default_permissions(...)` to restore the chat's configured
    default permissions when available.
    """
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=True,
        can_change_info=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )


async def get_chat_default_permissions(bot: Bot, chat_id: int) -> ChatPermissions:
    """
    Return the chat's default permissions when available; otherwise fall back to
    a permissive member set so verified users aren't left muted due to API
    lookup failures.
    """
    try:
        chat = await bot.get_chat(chat_id)
        perms = getattr(chat, "permissions", None)
        if perms:
            return perms
    except Exception:
        pass
    return full_member_permissions()

