import logging
import os

from fastapi import FastAPI, HTTPException, Request, Response
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import Update

from bot import dp, Settings


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")  # set to a secret-ish path in prod

app = FastAPI()


@app.on_event("startup")
async def on_startup() -> None:
    settings = Settings.from_env()
    bot = Bot(token=settings.bot_token, parse_mode=ParseMode.HTML)
    app.state.bot = bot
    logger.info("Webhook app started with path %s", WEBHOOK_PATH)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    bot: Bot | None = getattr(app.state, "bot", None)
    if bot:
        await bot.session.close()


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> Response:
    """FastACK webhook handler. Validates JSON -> aiogram Update -> feeds dispatcher."""
    bot: Bot | None = getattr(app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        payload = await request.json()
        update = Update.model_validate(payload)
    except Exception as exc:  # broad to return clear client error to Telegram
        logger.exception("Failed to parse update: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid update payload")

    await dp.feed_update(bot, update)
    return Response(status_code=200)
