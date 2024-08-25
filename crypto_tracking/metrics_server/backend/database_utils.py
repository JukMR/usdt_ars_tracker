from sqlalchemy import text

from crypto_tracking.metrics_server.backend.backend_flask_app import app
from crypto_tracking.metrics_server.backend.values_model import Values


def _get_db_engine():
    return app.config["DB_ENGINE"]


def read_latest_value() -> Values:
    """Read the latest value from the database"""
    db_engine = _get_db_engine()
    with db_engine.connect() as connection:
        results = connection.execute(text("SELECT * FROM entries ORDER BY datetime DESC LIMIT 1"))
        for row in results:
            timestamp, source, buy, sell = row
            return Values(timestamp=timestamp, source=source, buy=buy, sell=sell)

    raise ValueError("No values found in the database")
