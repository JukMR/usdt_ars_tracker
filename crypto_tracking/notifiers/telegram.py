"""Telegram Bot API notifier using plain HTTP.

The Bot API is a simple JSON endpoint; using ``requests`` directly avoids the
event-loop gymnastics required by asynchronous bot libraries.
"""

from __future__ import annotations

import os

import requests  # type: ignore[import-untyped]

from crypto_tracking.domain import Notification
from crypto_tracking.notifiers.base import Notifier, NotifierNotConfigured

DEFAULT_TIMEOUT = 15.0
MAX_MESSAGE_LENGTH = 4000


class TelegramNotifier(Notifier):
    channel = "telegram"

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self.bot_token = bot_token or os.environ.get("BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("CHAT_ID", "")
        self.timeout = timeout
        self._session = session or requests.Session()

        if not self.bot_token or not self.chat_id:
            raise NotifierNotConfigured("Telegram requires BOT_TOKEN and CHAT_ID")

    def send(self, notification: Notification) -> None:
        text = f"{notification.title}\n\n{notification.message}"[:MAX_MESSAGE_LENGTH]
        response = self._session.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=self.timeout,
        )
        if not response.ok:
            raise RuntimeError(f"Telegram API returned HTTP {response.status_code}: {response.text[:300]}")
