from pathlib import Path

from flask import Flask, Response, current_app, jsonify, request
from sqlalchemy import Engine, text

from crypto_tracking.metrics_server.backend.database.database_service import DatabaseService
from crypto_tracking.metrics_server.backend.values_model import Values

app = Flask(__name__)


def get_db_engine():
    return current_app.config["DB_ENGINE"]


def read_latest_value() -> Values:
    # This function should read the latest value from the database
    # and return it as a Values object

    db_engine = get_db_engine()
    with db_engine.connect() as connection:
        results = connection.execute(text("SELECT * FROM entries ORDER BY datetime DESC LIMIT 1"))
        for row in results:
            timestamp, source, buy, sell = row
            return Values(timestamp=timestamp, source=source, buy=buy, sell=sell)

    raise ValueError("No values found in the database")


@app.route("/metrics", methods=["GET"])
def get_current_price() -> Response:
    current_value: Values = read_latest_value()
    print(f"Fetched latest value and it is: {current_value}")

    return jsonify("current_value")


# Define a route to handle the numbers
@app.route("/api/numbers", methods=["POST"])
def set_alert_thresholds() -> Response:
    data = request.get_json()
    print("received post")

    min_num = data["min_num"]
    max_num = data["max_num"]
    # Process the numbers here (e.g., store them in a database, perform calculations, etc.)
    print(f"Received numbers: min={min_num}, max={max_num}")
    return jsonify({"message": "Numbers received successfully!"})


def run_backend(db_engine: Engine) -> None:
    app.config["DB_ENGINE"] = db_engine
    app.run(debug=True, port=5001)


def main() -> None:
    project_folder: Path = Path(__file__).resolve().parent.parent.parent
    assert project_folder.name == "crypto_tracking", "Project folder is not named 'crypto_tracking'"

    db_engine = DatabaseService(project_folder=project_folder).start()
    run_backend(db_engine=db_engine)


if __name__ == "__main__":
    main()
