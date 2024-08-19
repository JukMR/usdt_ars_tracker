import asyncio
import os

from telegram import Bot
from telegram.error import TelegramError

from crypto_tracking.logging_config import logger


def get_env_var(name: str) -> str:
    variable = os.environ.get(name)
    assert variable, "Variable not found"

    return variable


def send_bot_alert(msg: str) -> None:
    """Send an alert to the Telegram bot with the differences between the old and new data."""

    bot_token = get_env_var("BOT_TOKEN")
    chat_id = get_env_var("CHAT_ID")

    asyncio.run(send_alert(message=msg, bot_token=bot_token, chat_id=chat_id))


async def send_alert(message: str, bot_token: str, chat_id: str) -> None:
    """Send an alert to the Telegram bot."""

    bot = Bot(token=bot_token)
    try:
        await bot.send_message(chat_id=chat_id, text=message)
        logger.info("Alert sent successfully")

    except TelegramError as e:
        logger.error("Failed to send alert: %s", e)
