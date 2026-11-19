"""Notifier abstraction.

Add a new delivery channel by subclassing :class:`Notifier`, implementing
``send`` and registering an instance in the notifier registry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from crypto_tracking.domain import Notification


class NotifierNotConfigured(RuntimeError):
    """Raised when a notifier's credentials or settings are missing."""


class Notifier(ABC):
    """Base class for delivery channels such as Telegram, email or webhooks."""

    channel: ClassVar[str]

    @abstractmethod
    def send(self, notification: Notification) -> None:
        """Deliver a notification, raising on failure."""
