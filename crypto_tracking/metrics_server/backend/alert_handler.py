from enum import Enum, auto

from flask import Response, jsonify

from crypto_tracking.logging_config import logger
from crypto_tracking.metrics_server.backend.database_utils import read_latest_value
from crypto_tracking.metrics_server.backend.notifiers.notifier_abs import NotifierAbs
from crypto_tracking.metrics_server.backend.values_model import Values


class Operators(Enum):
    """The operators to use for the alert"""

    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="


class CurrencyType(Enum):
    BUY = auto()
    SELL = auto()


class Alert:
    def __init__(self, currency: str, currency_type: CurrencyType, threshold: float, operator: Operators) -> None:
        self.currency: str = currency
        self.currency_type: CurrencyType = currency_type
        self.threshold: float = threshold
        self.operator: Operators = operator
        self.alert_notifiers: list[NotifierAbs] = []

    def add_notifier(self, notifier: NotifierAbs) -> None:
        self.alert_notifiers.append(notifier)
        logger.info("Notifier %s added to alert", notifier)

    def remove_notifier(self, notifier: NotifierAbs) -> None:
        if self.alert_notifiers:
            self.alert_notifiers.remove(notifier)
            logger.info("Notifier %s removed from alert", notifier)

        logger.info("No notifiers to remove")

    def check(self, data: Values) -> bool:
        value: float = data.buy if self.currency_type == CurrencyType.BUY else data.sell
        match self.operator:
            case Operators.LESS_THAN:
                return value < self.threshold
            case Operators.LESS_THAN_OR_EQUAL:
                return value <= self.threshold
            case Operators.EQUAL:
                return value == self.threshold
            case Operators.GREATER_THAN:
                return value > self.threshold
            case Operators.GREATER_THAN_OR_EQUAL:
                return value >= self.threshold
            case _:
                return False

    def send_alert(self) -> None:
        if not self.alert_notifiers:
            logger.error("No notifiers added to alert")
            return

        for notifier in self.alert_notifiers:
            current_value: Values = read_latest_value()

            current_value_float: float = (
                current_value.buy if self.currency_type == CurrencyType.BUY else current_value.sell
            )

            notifier.send_alert(
                msg=f"Alert: {self.currency} for {self.currency_type.name} and value is {current_value_float}"
            )
            logger.info("Alert sent to %s", notifier)

    def to_json(self) -> dict:
        """Convert the alert to a dict"""
        return {
            "currency": self.currency,
            "currency_type": self.currency_type.name,
            "threshold": self.threshold,
            "operator": self.operator.value,
            "alert_notifiers": [str(notifier.__class__.__name__) for notifier in self.alert_notifiers],
        }


class Alerter:
    def __init__(self) -> None:
        self._alerts: list[Alert] = []

    def check_alerts(self, data: Values) -> None:
        for alert in self._alerts:
            if alert.check(data):
                alert.send_alert()

    def add_alert(self, alert: Alert, notifiers: list[NotifierAbs]) -> None:
        for notifier in notifiers:
            alert.add_notifier(notifier)
        self._alerts.append(alert)

    def get_alerts(self) -> list[Alert]:
        """Get the current alerts as a list of dicts"""
        return self._alerts

    def get_alert_by_id(self, alert_id: int) -> Alert | None:
        """Get an alert by its id, which is the index of the alert in the list"""
        if alert := self._alerts[alert_id]:
            return alert

        logger.error("Alert not found for id %s", alert_id)
        return None

    def delete_alert(self, alert_id: int) -> bool:
        """Delete an alert by its id"""
        if alert := self.get_alert_by_id(alert_id):
            self._alerts.remove(alert)
            return True

        logger.error("Alert not found")
        return False

    def delete_all_alerts(self) -> None:
        """Delete all alerts"""
        self._alerts = []


# Initialize the alerter instance
alerter_instance = Alerter()


class AlertThresholdSetter:
    def __init__(
        self, data: dict, alerter: Alerter, currency_type: CurrencyType, notifiers_list: list[NotifierAbs]
    ) -> None:
        self.data = data
        self.alerter: Alerter = alerter
        self.min_num: str | None = data.get("min_num")
        self.max_num: str | None = data.get("max_num")
        self.currency_type: CurrencyType = currency_type
        self.notifiers_list: list[NotifierAbs] = notifiers_list

    def set_alert(self) -> Response:
        """Set the alert thresholds for the minimum and maximum values"""
        if self.min_num is None and self.max_num is None:
            return jsonify({"error": "Please provide min_num or max_num"})

        if self.min_num is not None and self.max_num is not None:
            self._set_minimum_threshold(self.min_num, currency_type=self.currency_type)
            self._set_maximum_threshold(self.max_num, currency_type=self.currency_type)

            return jsonify(
                {
                    "message": f"Min alert set successfully to {self.min_num} and Max alert set successfully to {self.max_num}"
                }
            )

        if self.min_num is not None:
            self._set_minimum_threshold(self.min_num, currency_type=self.currency_type)
            return jsonify({"message": f"Min alert set successfully to {self.min_num}"})

        if self.max_num is not None:
            self._set_maximum_threshold(self.max_num, currency_type=self.currency_type)

            return jsonify({"message": f"Max alert set successfully to {self.max_num}"})

        raise ValueError("Invalid input")

    def _set_minimum_threshold(self, min_num: str, currency_type: CurrencyType) -> None:
        """Set the minimum threshold for the alert"""
        min_num_float = float(min_num)
        self.alerter.add_alert(
            alert=Alert(
                currency="USDT", currency_type=currency_type, threshold=min_num_float, operator=Operators.LESS_THAN
            ),
            notifiers=self.notifiers_list,
        )

    def _set_maximum_threshold(self, max_num: str, currency_type: CurrencyType) -> None:
        """Set the maximum threshold for the alert"""
        max_num_float = float(max_num)
        self.alerter.add_alert(
            alert=Alert(
                currency="USDT", currency_type=currency_type, threshold=max_num_float, operator=Operators.GREATER_THAN
            ),
            notifiers=self.notifiers_list,
        )
