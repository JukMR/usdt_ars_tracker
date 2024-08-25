import time
from pathlib import Path
from threading import Thread
from typing import NoReturn

from flask import Response, jsonify, request
from sqlalchemy import Engine

from crypto_tracking.logging_config import logger
from crypto_tracking.metrics_server.backend.alert_handler import (
    Alert,
    AlertThresholdSetter,
    CurrencyType,
    alerter_instance,
)
from crypto_tracking.metrics_server.backend.backend_flask_app import app
from crypto_tracking.metrics_server.backend.database.database_service import DatabaseService
from crypto_tracking.metrics_server.backend.database_utils import read_latest_value
from crypto_tracking.metrics_server.backend.notifiers.notifier_abs import NotifierAbs
from crypto_tracking.metrics_server.backend.notifiers.telegram_notifier import TelegramNotifier
from crypto_tracking.metrics_server.backend.values_model import Values


@app.route("/metrics", methods=["GET"])
def get_current_price() -> Response:
    """Get the current price of the cryptocurrency"""
    current_value: Values = read_latest_value()
    return jsonify(f"data: {current_value}")


# Define a route to handle the numbers
@app.route("/api/numbers", methods=["POST"])
def set_alert_thresholds() -> Response:
    """Set the alert thresholds for the minimum and maximum values"""
    data: dict | None = request.get_json()
    if data is None:
        return jsonify({"error": "No data provided"})

    currency_type_raw: str | None = data.get("currency_type")
    if currency_type_raw is None:
        return jsonify({"error": "Please provide currency_type"})

    if currency_type_raw not in ["buy", "sell"]:
        return jsonify({"error": "Invalid currency_type"})

    match currency_type_raw:
        case "buy":
            currency_type = CurrencyType.BUY
        case "sell":
            currency_type = CurrencyType.SELL
        case _:
            return jsonify({"error": "Invalid currency_type"})

    # Use telegram notifiers as default
    notifiers: list[NotifierAbs] = [TelegramNotifier()]
    return AlertThresholdSetter(
        data=data, currency_type=currency_type, alerter=alerter_instance, notifiers_list=notifiers
    ).set_alert()


@app.route("/api/alerts", methods=["GET"])
def get_current_alerts() -> Response:
    """Get the current alerts"""
    alerts: list[Alert] = alerter_instance.get_alerts()
    return jsonify({"data": [alert.to_json() for alert in alerts]})


def run_backend(db_engine: Engine) -> None:
    app.config["DB_ENGINE"] = db_engine

    check_alerts_thread = Thread(target=check_alerts)
    check_alerts_thread.start()

    app.run(debug=True, port=5001)


def check_alerts() -> NoReturn:
    """Check for alerts"""

    time.sleep(1)
    while True:
        logger.info("Checking for alerts")
        value: Values = read_latest_value()
        alerter_instance.check_alerts(data=value)
        time.sleep(60)


def main() -> None:
    project_folder: Path = Path(__file__).resolve().parent.parent.parent
    assert project_folder.name == "crypto_tracking", "Project folder is not named 'crypto_tracking'"

    db_engine = DatabaseService(project_folder=project_folder).start()
    run_backend(db_engine=db_engine)


if __name__ == "__main__":
    main()
