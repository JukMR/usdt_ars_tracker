from abc import ABC, abstractmethod


class NotifierAbs(ABC):
    @abstractmethod
    def send_alert(self, msg: str) -> None:
        """Send a message to the bot"""
