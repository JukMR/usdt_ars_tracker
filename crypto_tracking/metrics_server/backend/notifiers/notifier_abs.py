from abc import ABC, abstractmethod


class NotifierAbs(ABC):
    """Base class for implementing notifiers which send alerts."""

    @abstractmethod
    def send_alert(self, msg: str) -> None:
        """Send a message to the bot"""
