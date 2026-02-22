import asyncio

from telegram import Bot
from telegram.error import TelegramError

from crypto_tracking.logging_config import logger
from crypto_tracking.metrics_server.backend.env_helper import EnvHelper
from crypto_tracking.metrics_server.backend.notifiers.notifier_abs import NotifierAbs


class TelegramNotifier(NotifierAbs):
    """Implementation of the NotifierAbs class for sending alert to Telegram group."""

    def __init__(self) -> None:
        self._env_helper = EnvHelper()
        self._bot_token: str = self._env_helper.get_env_var("BOT_TOKEN")
        self._chat_id: str = self._env_helper.get_env_var("CHAT_ID")

    def send_alert(self, msg: str) -> None:
        """Send an alert to the Telegram bot with the differences between the old and new data."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.send_async_alert(message=msg, bot_token=self._bot_token, chat_id=self._chat_id))
            else:
                loop.run_until_complete(self.send_async_alert(message=msg, bot_token=self._bot_token, chat_id=self._chat_id))
        except RuntimeError:
            asyncio.run(self.send_async_alert(message=msg, bot_token=self._bot_token, chat_id=self._chat_id))

    async def send_async_alert(self, message: str, bot_token: str, chat_id: str) -> None:
        """Send an alert to the Telegram bot."""
        bot = Bot(token=bot_token)
        try:
            await bot.send_message(chat_id=chat_id, text=message)
            logger.info("Alert sent successfully to Telegram")

        except TelegramError as e:
            logger.error("Failed to send Telegram alert: %s", e)
        except Exception as e:
            logger.error("Unexpected error sending Telegram alert: %s", e)
