"""Always-available notifier that writes alerts to the application log."""

from __future__ import annotations

import logging

from crypto_tracking.domain import Notification
from crypto_tracking.notifiers.base import Notifier

logger = logging.getLogger(__name__)


class LogNotifier(Notifier):
    """Useful in offline mode and as a fallback when no external channel is set up."""

    channel = "log"

    def send(self, notification: Notification) -> None:
        logger.info("ALERT | %s | %s", notification.title, notification.message)
