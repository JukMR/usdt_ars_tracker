from dataclasses import dataclass
from enum import Enum

from flask import Response, jsonify

from crypto_tracking.logging_config import logger
from crypto_tracking.metrics_server.backend.notifiers.telegram import send_bot_alert


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
                logger.info(f"Sending email alert for {self.currency} {self.operator} {self.value}")
            case Notifier.TELEGRAM:
                logger.info(f"Sending telegram alert for {self.currency} {self.operator} {self.value}")
                send_bot_alert(msg="Alert triggered")

            case _:
                logger.info(f"Unknown alert type: {self.alert_type}")


class Alerter:
    def __init__(self) -> None:
        self.alerts = []

    def check_alerts(self, data: dict) -> None:
        for alert in self.alerts:
            if alert.check(data):
                alert.send_alert()

    def add_alert(self, alert: Alert) -> None:
        self.alerts.append(alert)


# Initialize the alerter instance
alerter_instance = Alerter()


class AlertThresholdSetter:
    def __init__(self, data: dict, alerter: Alerter) -> None:
        self.data = data
        self.alerter: Alerter = alerter
        self.min_num: str | None = data.get("min_num")
        self.max_num: str | None = data.get("max_num")

    def set_alert(self) -> Response:
        if self.min_num is None and self.max_num is None:
            return jsonify({"error": "Please provide min_num or max_num"})

        if self.min_num is not None and self.max_num is not None:
            self.set_minimum_threshold(self.min_num)
            self.set_maximum_threshold(self.max_num)
            return jsonify(
                {
                    "message": f"Min alert set successfully to {self.min_num} and Max alert set successfully to {self.max_num}"
                }
            )

        if self.min_num is not None:
            self.set_minimum_threshold(self.min_num)
            return jsonify({"message": f"Min alert set successfully to {self.min_num}"})

        if self.max_num is not None:
            self.set_maximum_threshold(self.max_num)
            return jsonify({"message": f"Max alert set successfully to {self.max_num}"})

        raise ValueError("Invalid input")

    def set_minimum_threshold(self, min_num: str) -> None:
        """Set the minimum threshold for the alert"""
        min_num_float = float(min_num)
        self.alerter.add_alert(Alert("USDT", min_num_float, Operators.LESS_THAN, Notifier.EMAIL))

    def set_maximum_threshold(self, max_num: str) -> None:
        """Set the maximum threshold for the alert"""
        max_num_float = float(max_num)
        self.alerter.add_alert(Alert("USDT", max_num_float, Operators.GREATER_THAN, Notifier.EMAIL))
