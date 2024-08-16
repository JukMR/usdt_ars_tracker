from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from crypto_tracking.metrics_server.backend.database.sql_models import Entry
from crypto_tracking.metrics_server.backend.values_model import Values


class DatabaseSession:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.session = None

    def __enter__(self) -> Any:
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.session.commit()
        self.session.close()


class DatabasePopulator:
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
        data_folder: Path = self.project_folder / "data"
        assert data_folder.exists(), f"Data folder not found: {data_folder}"

        exchange_rate_file: Path = data_folder / "exchange_rates.csv"
        assert exchange_rate_file.exists(), f"Exchange rate file not found: {exchange_rate_file}"

        # Load data from CSV file

        df = pd.read_csv(exchange_rate_file)
        values: list[Values] = df.to_dict(orient="records")

        values = [Values.model_validate(value) for value in values]

        return values
