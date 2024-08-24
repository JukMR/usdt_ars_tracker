import asyncio

from telegram import Bot
from telegram.error import TelegramError

from crypto_tracking.logging_config import logger
from crypto_tracking.metrics_server.backend.env_helper import EnvHelper
from crypto_tracking.metrics_server.backend.notifiers.notifier_abs import NotifierAbs


class TelegramNotifier(NotifierAbs):
    def send_alert(self, msg: str) -> None:
        """Send an alert to the Telegram bot with the differences between the old and new data."""

        _env_helper = EnvHelper()
        bot_token: str = _env_helper.get_env_var("BOT_TOKEN")
        chat_id: str = _env_helper.get_env_var("CHAT_ID")

        asyncio.run(self.send_async_alert(message=msg, bot_token=bot_token, chat_id=chat_id))

    @staticmethod
    async def send_async_alert(message: str, bot_token: str, chat_id: str) -> None:
        """Send an alert to the Telegram bot."""

        bot = Bot(token=bot_token)
        try:
            await bot.send_message(chat_id=chat_id, text=message)
            logger.info("Alert sent successfully")

        except TelegramError as e:
            logger.error("Failed to send alert: %s", e)
