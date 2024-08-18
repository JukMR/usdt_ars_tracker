from dataclasses import dataclass
from enum import Enum


class Operators(Enum):
    """The operators to use for the alert"""

    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="


class Notifier(Enum):
    """The type of notifier to use for the alert"""

    EMAIL = "email"
    TELEGRAM = "telegram"


@dataclass
class Alert:
    currency: str
    value: float
    operator: Operators
    alert_type: Notifier

    def check(self, data: dict) -> bool:
        match self.operator:
            case Operators.LESS_THAN:
                return data[self.currency] < self.value
            case Operators.LESS_THAN_OR_EQUAL:
                return data[self.currency] <= self.value
            case Operators.EQUAL:
                return data[self.currency] == self.value
            case Operators.GREATER_THAN:
                return data[self.currency] > self.value
            case Operators.GREATER_THAN_OR_EQUAL:
                return data[self.currency] >= self.value
            case _:
                return False

    def send_alert(self) -> None:
        match self.alert_type:
            case Notifier.EMAIL:
                print(f"Sending email alert for {self.currency} {self.operator} {self.value}")
            case Notifier.TELEGRAM:
                print(f"Sending telegram alert for {self.currency} {self.operator} {self.value}")
            case _:
                print(f"Unknown alert type: {self.alert_type}")


class Alerter:
    def __init__(self) -> None:
        self.alerts = []

    def check_alerts(self, data: dict) -> None:
        for alert in self.alerts:
            if alert.check(data):
                alert.send_alert()

    def add_alert(self, Alert: Alert) -> None:
        self.alerts.append(Alert)


alerter_instance = Alerter()
