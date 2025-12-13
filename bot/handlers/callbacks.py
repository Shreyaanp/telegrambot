"""Callback handlers for inline buttons."""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery

logger = logging.getLogger(__name__)

router = Router()


async def handle_callback(callback: CallbackQuery):
    """Handle callback queries from inline buttons."""
    # For now, just acknowledge the callback
    # Deep links and app downloads are handled by URL buttons (no callback needed)
    await callback.answer()
    logger.debug(f"Callback query from {callback.from_user.id}: {callback.data}")


def register_callback_handlers(router: Router):
    """Register all callback handlers."""
    router.callback_query.register(handle_callback)

