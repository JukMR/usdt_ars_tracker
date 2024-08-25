from typing import Final

import requests
from flask import Flask, Response, jsonify, render_template, request

from crypto_tracking.metrics_server.backend.alert_handler import Alert

app = Flask(__name__)

BACKEND_LOCAL_URL: Final[str] = "http://localhost:5001"


@app.route("/", methods=["GET", "POST"])
def home() -> str:
    return render_template("main.html")


@app.route("/threshold", methods=["GET", "POST"])
def set_threshold() -> str:
    match request.method:
        case "GET":
            return render_template("threshold.html")

        case "POST":
            min_num = request.form["min_num"]
            max_num = request.form["max_num"]
            currency_type = request.form["currency_type"]

            # Send the numbers to the backend server
            response = requests.post(
                BACKEND_LOCAL_URL + "/api/numbers",
                json={"min_num": min_num, "max_num": max_num, "currency_type": currency_type},
                timeout=60,
            )
            response.raise_for_status()
            return "Numbers sent successfully!"

        case _:
            return "Invalid request method"


def get_current_alerts() -> list[Alert]:
    response = requests.get(BACKEND_LOCAL_URL + "/api/alerts", timeout=60)
    response.raise_for_status()
    alerts: list[dict] = response.json()["data"]
    alert_with_id: list[dict] = [{"id": i, **alert} for i, alert in enumerate(alerts)]

    return alert_with_id


@app.route("/delete/alerts", methods=["DELETE"])
def delete_alerts() -> Response:
    response = requests.delete(BACKEND_LOCAL_URL + "/delete/alerts", timeout=60)
    response.raise_for_status()
    return jsonify(response.json())


@app.route("/delete/alert/<int:alert_id>", methods=["DELETE"])
def delete_alert(alert_id: int) -> Response:
    response = requests.delete(BACKEND_LOCAL_URL + f"/delete/alert/{alert_id}", timeout=60)
    response.raise_for_status()
    return jsonify(response.json())


@app.route("/alerts", methods=["GET", "POST"])
def alerts() -> str:
    match request.method:
        case "GET":
            current_alerts: list[Alert] = get_current_alerts()
            return render_template("alerts.html", alerts=current_alerts)

        case "POST":
            raise NotImplementedError("POST method not implemented")
        case _:
            return "Invalid request method"


def main() -> None:
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()
