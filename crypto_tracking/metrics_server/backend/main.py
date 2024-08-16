from pathlib import Path

from flask import Flask, Response, jsonify, request
from sqlalchemy import Engine

from crypto_tracking.metrics_server.backend.database.database_service import DatabaseService
from crypto_tracking.metrics_server.backend.values_model import Values

app = Flask(__name__)


def read_latest_value(db_engine: Engine) -> Values:
    # This function should read the latest value from the database
    # and return it as a Values object

    with db_engine.connect() as connection:
        results = connection.execute(text("SELECT * FROM entry ORDER BY date DESC LIMIT 1"))
        for row in results:
            assert len(results) <= 1, f"Expected at most 1 result, but got {len(results)}"
            return Values(timestamp=row["date"], source=row["source"], buy=row["buy"], sell=row["sell"])

    raise ValueError("No values found in the database")


@app.route("/metrics", methods=["GET"])
def get_current_price():
    current_value: Values = read_latest_value(db_engine=db_engine)
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


if __name__ == "__main__":
    project_folder: Path = Path(__file__).resolve().parent.parent.parent

    assert (
        project_folder.name == "crypto_tracking"
    ), f"Expected project folder to be 'crypto_tracking', but got {project_folder.name}"

    db_engine: Engine = DatabaseService(project_folder=project_folder).start()

    app.run(debug=True, port=5001)
