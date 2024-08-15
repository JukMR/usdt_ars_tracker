from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from crypto_tracking.metrics_server.backend.database.sql_models import Base, Entry
from crypto_tracking.metrics_server.backend.values_model import Values

project_folder_path = Path(__file__).resolve().parents[2]
assert project_folder_path.name == "crypto_tracking"


def load_total_values(project_folder: Path) -> list[Values]:
    data_folder: Path = project_folder / "data"
    assert data_folder.exists(), f"Data folder not found: {data_folder}"

    exchange_rate_file: Path = data_folder / "exchange_rates.csv"
    assert exchange_rate_file.exists(), f"Exchange rate file not found: {exchange_rate_file}"

    # Load data from CSV file

    df = pd.read_csv(exchange_rate_file)
    values: list[Values] = df.to_dict(orient="records")

    values = [Values.model_validate(value) for value in values]
    return values


def create_database() -> None:
    """Create the database and tables"""

    engine = create_engine("sqlite:///crypto_tracking.db")
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # Load values from CSV
    values = load_total_values(project_folder=project_folder_path)

    # Insert values into database
    for value in values:
        entry = Entry(date=value.timestamp, source=value.source, buy=value.buy, sell=value.sell)
        session.add(entry)

    session.commit()
    session.close()
