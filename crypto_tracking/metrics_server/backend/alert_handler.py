from enum import Enum

from flask import Response, jsonify

from crypto_tracking.logging_config import logger
from crypto_tracking.metrics_server.backend.notifiers.notifier_abs import NotifierAbs


class Operators(Enum):
    """The operators to use for the alert"""

    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="


class Alert:
    def __init__(self, currency: str, value: float, operator: Operators) -> None:
        self.currency: str = currency
        self.value: float = value
        self.operator: Operators = operator
        self.alert_notifiers: list[NotifierAbs] | None

    def add_notifier(self, notifier: NotifierAbs) -> None:
        if self.alert_notifiers is None:
            self.alert_notifiers = []
        self.alert_notifiers.append(notifier)
        logger.info("Notifier %s added to alert", notifier)

    def remove_notifier(self, notifier: NotifierAbs) -> None:
        if self.alert_notifiers is not None:
            self.alert_notifiers.remove(notifier)
            logger.info("Notifier %s removed from alert", notifier)

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
        if self.alert_notifiers is None:
            logger.error("No notifiers added to alert")
            return

        for notifier in self.alert_notifiers:
            notifier.send_alert(msg=f"Alert: {self.currency} value is {self.value}")
            logger.info("Alert sent to %s", notifier)


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
        self.alerter.add_alert(Alert(currency="USDT", value=min_num_float, operator=Operators.LESS_THAN))

    def set_maximum_threshold(self, max_num: str) -> None:
        """Set the maximum threshold for the alert"""
        max_num_float = float(max_num)
        self.alerter.add_alert(Alert(currency="USDT", value=max_num_float, operator=Operators.GREATER_THAN))
