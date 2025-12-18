"""Middleware to handle anonymous admin messages safely.

Telegram supports “anonymous admins” (messages sent as a chat via `sender_chat`).
In that case, `from_user` may be missing and most bot commands cannot be
authorized reliably. This middleware prevents crashes and gives a clear hint.
"""

from __future__ import annotations

from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Message


class AnonymousAdminGuardMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data):  # type: ignore[override]
        if isinstance(event, Message) and event.chat and event.chat.type in ("group", "supergroup") and event.from_user is None:
            text = (event.text or "").strip()
            # Only reply for commands to avoid spamming on regular chat messages.
            if text.startswith("/"):
                try:
                    await event.reply(
                        "❌ I can't verify permissions for anonymous admins.\n\n"
                        "Disable <b>Remain anonymous</b> in the group admin settings, then try again.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            return

        return await handler(event, data)

