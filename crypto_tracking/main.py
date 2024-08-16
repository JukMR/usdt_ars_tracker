"""Main module that fetches and stores the exchange rate from Buenbit."""

import csv
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

import schedule

from crypto_tracking.api_poller.poller import fetch_exchange_rate
from crypto_tracking.logging_config import configure_logger, logger
from crypto_tracking.metrics_server.backend import backend_main
from crypto_tracking.metrics_server.backend.backend_main import run_backend
from crypto_tracking.metrics_server.backend.database.database_service import DatabaseService, Engine
from crypto_tracking.metrics_server.backend.database.database_session import DatabaseSession
from crypto_tracking.metrics_server.backend.database.sql_models import Entry
from crypto_tracking.metrics_server.frontend.frontend_main import run_frontend


class Storer:
    def __init__(self, data_folder: Path, polling_rate: int, project_folder: Path, db_engine: Engine) -> None:
        self.data_folder: Path = data_folder
        self.polling_rate: int = polling_rate
        self.project_folder: Path = project_folder

        self.database_engine: Engine = DatabaseService(project_folder=self.project_folder).start()

    def job(
        self,
    ) -> None:
        logger.info("Fetching exchange rate...")
        rate_data: dict[str, Any] = fetch_exchange_rate(polling_rate=self.polling_rate)
        if rate_data:
            buy = float(rate_data["totalAsk"])
            sell = float(rate_data["totalBid"])

            source: str = "buenbit"
            current_time: datetime = datetime.now()
            self.store(current_time=current_time, source=source, buy=buy, sell=sell)

            logger.info("Stored new buy: %s at %s", rate_data["totalAsk"], current_time)
            logger.info("Stored new sell: %s at %s", rate_data["totalBid"], current_time)

    def store(self, source: str, buy: float, sell: float, current_time: datetime) -> None:
        self.insert_entry_in_database(current_time=current_time, source=source, buy=buy, sell=sell)

    def insert_entry_in_database(self, current_time: datetime, source: str, buy: float, sell: float) -> None:
        """Insert the fetched exchange rate into a database."""
        with DatabaseSession(engine=self.database_engine) as db_service:
            db_service.add(Entry(datetime=current_time, source=source, buy=buy, sell=sell))


def prepare_database(project_folder: Path) -> Engine:
    return DatabaseService(project_folder=project_folder).start()


def poller(project_folder: Path, db_engine: Engine) -> NoReturn:
    data_folder: Path = project_folder / "data"
    assert data_folder.exists(), f"Data folder {data_folder} does not exist"

    polling_rate: int = 60
    job_instance: Storer = Storer(
        data_folder=data_folder, polling_rate=polling_rate, project_folder=project_folder, db_engine=db_engine
    )

    schedule.every(polling_rate).seconds.do(job_instance.job)

    logger.info("Starting exchange rate tracking app...")

    while True:
        try:
            schedule.run_pending()

        except Exception as exc:  # pylint: disable=broad-except
            logger.info("An error occurred: %s", exc)

        finally:
            time.sleep(5)


def main() -> None:
    """Main function that starts the exchange rate tracking app."""

    # Configure project folders
    project_folder: Path = Path(__file__).resolve().parent
    assert project_folder.name == "crypto_tracking", "Project folder is not named 'crypto_tracking'"

    data_folder: Path = project_folder / "data"
    data_folder.mkdir(exist_ok=True)

    # Configure logger
    configure_logger(project_folder=project_folder)

    # Main code

    database: Engine = prepare_database(project_folder=project_folder)

    # Run these tasks asyncronously on separate thread
    # Run the poller
    poller_thread = threading.Thread(target=poller, kwargs={"project_folder": project_folder, "db_engine": database})
    poller_thread.start()

    # Run the backend
    backend_thread = threading.Thread(target=run_backend, kwargs={"db_engine": database})
    backend_thread.start()

    # Run the frontend
    frontend_thread = threading.Thread(target=run_frontend)
    frontend_thread.start()


if __name__ == "__main__":
    main()
