from typing import Final, Union

import requests  # type: ignore[import-untyped]
from flask import Flask, Response, jsonify, render_template, request
from requests.exceptions import ConnectionError, Timeout, HTTPError  # type: ignore[import-untyped]

from crypto_tracking.logging_config import logger

app = Flask(__name__)

BACKEND_LOCAL_URL: Final[str] = "http://localhost:5001"
REQUEST_TIMEOUT: Final[int] = 30


@app.route("/", methods=["GET", "POST"])
def home() -> str:
    return render_template("main.html")


@app.route("/threshold", methods=["GET", "POST"])
def set_threshold() -> Union[str, tuple[str, int]]:
    match request.method:
        case "GET":
            return render_template("threshold.html")

        case "POST":
            min_num = request.form["min_num"]
            max_num = request.form["max_num"]
            currency_type = request.form["currency_type"]

            try:
                response = requests.post(
                    BACKEND_LOCAL_URL + "/api/numbers",
                    json={"min_num": min_num, "max_num": max_num, "currency_type": currency_type},
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                logger.info("Alert thresholds set successfully")
                return "Numbers sent successfully!"

            except ConnectionError:
                logger.error("Failed to connect to backend server at %s", BACKEND_LOCAL_URL)
                return "Error: Cannot connect to backend server. Ensure it's running.", 503

            except Timeout:
                logger.error("Request to backend server timed out")
                return "Error: Request timed out. Please try again.", 504

            except HTTPError as e:
                logger.error("HTTP error from backend: %s", e)
                return f"Error: Backend returned error {e.response.status_code}", 500

            except Exception as e:
                logger.error("Unexpected error setting thresholds: %s", e)
                return "Error: An unexpected error occurred. Please try again.", 500

        case _:
            return "Invalid request method", 405


def get_current_alerts() -> list[dict]:
    try:
        response = requests.get(BACKEND_LOCAL_URL + "/api/alerts", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        alerts_dict: list[dict] = response.json()["data"]
        alert_with_id: list[dict] = [{"id": i, **alert} for i, alert in enumerate(alerts_dict)]
        return alert_with_id

    except ConnectionError:
        logger.error("Failed to connect to backend server while fetching alerts")
        return []

    except (Timeout, HTTPError, KeyError, ValueError) as e:
        logger.error("Error fetching alerts: %s", e)
        return []


@app.route("/delete/alerts", methods=["DELETE"])
def delete_alerts() -> Union[Response, tuple[Response, int]]:
    try:
        response = requests.delete(BACKEND_LOCAL_URL + "/delete/alerts", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return jsonify(response.json())

    except (ConnectionError, Timeout, HTTPError) as e:
        logger.error("Error deleting all alerts: %s", e)
        return jsonify({"error": "Failed to delete alerts"}), 500


@app.route("/delete/alert/<int:alert_id>", methods=["DELETE"])
def delete_alert(alert_id: int) -> Union[Response, tuple[Response, int]]:
    try:
        response = requests.delete(BACKEND_LOCAL_URL + f"/delete/alert/{alert_id}", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return jsonify(response.json())

    except (ConnectionError, Timeout, HTTPError) as e:
        logger.error("Error deleting alert %s: %s", alert_id, e)
        return jsonify({"error": "Failed to delete alert"}), 500


@app.route("/alerts", methods=["GET", "POST"])
def alerts() -> Union[str, tuple[str, int]]:
    match request.method:
        case "GET":
            current_alerts: list[dict] = get_current_alerts()
            return render_template("alerts.html", alerts=current_alerts)

        case "POST":
            raise NotImplementedError("POST method not implemented")
        case _:
            return "Invalid request method", 405


def main() -> None:
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()
