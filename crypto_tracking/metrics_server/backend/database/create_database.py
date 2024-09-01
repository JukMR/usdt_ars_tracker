from pathlib import Path

import csv
from sqlalchemy import Engine

from crypto_tracking.metrics_server.backend.database.database_session import DatabaseSession
from crypto_tracking.metrics_server.backend.database.sql_models import Entry
from crypto_tracking.metrics_server.backend.values_model import Values


class DatabaseFromCSVPopulator:
    """Populate the database using the values from the CSV file"""

    def __init__(self, project_folder: Path, db_engine: Engine) -> None:
        self.project_folder: Path = project_folder
        self.db_engine: Engine = db_engine

    def populate_database(self) -> None:
        """Populate the database with values"""

        # Load values from CSV
        values: list[Values] = self.load_total_values()

        with DatabaseSession(engine=self.db_engine) as session:
            for value in values:
                entry = Entry(datetime=value.timestamp, source=value.source, buy=value.buy, sell=value.sell)
                session.add(entry)

    def load_total_values(self) -> list[Values]:
        """Load values from the CSV file, validate them and return them as a list of Values objects"""
        data_folder: Path = self.project_folder / "data"
        assert data_folder.exists(), f"Data folder not found: {data_folder}"

        exchange_rate_file: Path = data_folder / "exchange_rates.csv"
        assert exchange_rate_file.exists(), f"Exchange rate file not found: {exchange_rate_file}"

        # Load data from CSV file

        values: list[Values] = []

        with open(exchange_rate_file, "w", newline="") as f:
            reader: csv.DictReader = csv.DictReader(f)
            for row in reader:
                values.append(
                    Values(
                        sell=row.get("sell"),
                        buy=row.get("buy"),
                        timestamp=row.get("timestamp"),
                        source=row.get("source"),
                    )
                )

        values = [Values.model_validate(value) for value in values]

        return values
