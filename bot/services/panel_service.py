"""Panel service - single-message DM panels (edit-in-place)."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select

from database.db import db
from database.models import DmPanelState

logger = logging.getLogger(__name__)


class PanelService:
    """Maintains persistent DM panels by editing one message per panel type."""

    async def upsert_dm_panel(
        self,
        *,
        bot: Bot,
        user_id: int,
        panel_type: str,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        group_id: Optional[int] = None,
    ) -> int:
        async with db.session() as session:
            result = await session.execute(
                select(DmPanelState).where(
                    DmPanelState.telegram_id == user_id,
                    DmPanelState.panel_type == panel_type,
                    DmPanelState.group_id == group_id,
                )
            )
            state = result.scalar_one_or_none()

            if state:
                try:
                    await bot.edit_message_text(
                        chat_id=user_id,
                        message_id=int(state.message_id),
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    return int(state.message_id)
                except Exception as e:
                    logger.debug(f"Failed to edit DM panel (will resend): {e}")

            sent = await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            if state:
                state.message_id = sent.message_id
            else:
                session.add(
                    DmPanelState(
                        telegram_id=user_id,
                        panel_type=panel_type,
                        group_id=group_id,
                        message_id=sent.message_id,
                    )
                )
            return sent.message_id

