import asyncio
import logging
import os
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message


@dataclass
class Settings:
    bot_token: str

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("BOT_TOKEN")
        if not token:
            raise RuntimeError("BOT_TOKEN env var is required")
        return cls(bot_token=token)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

dp = Dispatcher()


@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Hey! I'm alive. Try /help for what I can do.",
        parse_mode=ParseMode.HTML,
    )


@dp.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(
        "Commands:\n"
        "/start - greet\n"
        "/help  - this message\n"
        "Send any text and I will echo it back.",
    )


@dp.message()
async def handle_echo(message: Message) -> None:
    text = message.text or "<non-text message>"
    await message.answer(f"Echo: {text}")


async def main() -> None:
    settings = Settings.from_env()
    bot = Bot(token=settings.bot_token, parse_mode=ParseMode.HTML)
    logger.info("Starting bot with polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
