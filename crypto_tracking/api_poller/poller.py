"""Main module that fetches and stores the exchange rate from Buenbit."""

import time
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

import requests
import schedule

from crypto_tracking.logging_config import configure_logger, logger
from crypto_tracking.metrics_server.backend.database.database_service import DatabaseService, Engine
from crypto_tracking.metrics_server.backend.database.database_session import DatabaseSession
from crypto_tracking.metrics_server.backend.database.sql_models import Entry


def poller(project_folder: Path, db_engine: Engine, polling_rate: int = 60) -> NoReturn:
    """Poller function that fetches the exchange rate and stores it in the database."""
    job_instance: JobWorker = JobWorker(polling_rate=polling_rate, project_folder=project_folder, db_engine=db_engine)

    schedule.every(polling_rate).seconds.do(job_instance.job)

    logger.info("Starting exchange rate tracking app...")

    while True:
        try:
            schedule.run_pending()

        except Exception as exc:  # pylint: disable=broad-except
            logger.info("An error occurred: %s", exc)

        finally:
            time.sleep(5)


class JobWorker:
    """Class that fetches the prices of the USDT from buenbit and store it in the sqlite db"""

    def __init__(self, polling_rate: int, project_folder: Path, db_engine: Engine) -> None:
        self.polling_rate: int = polling_rate
        self.project_folder: Path = project_folder

        self.database_engine: Engine = db_engine

    def job(
        self,
    ) -> None:
        """Fetch the exchange rate and store it in the database."""
        logger.info("Fetching exchange rate...")
        rate_data: dict[str, Any] = self._fetch_exchange_rate(polling_rate=self.polling_rate)
        if rate_data:
            buy = float(rate_data["totalAsk"])
            sell = float(rate_data["totalBid"])

            source: str = "buenbit"
            current_time: datetime = datetime.now()
            self.store(current_time=current_time, source=source, buy=buy, sell=sell)

            logger.info("Stored new buy: %s at %s", rate_data["totalAsk"], current_time)
            logger.info("Stored new sell: %s at %s", rate_data["totalBid"], current_time)

    @staticmethod
    def _fetch_exchange_rate(polling_rate: int) -> dict[str, Any]:
        """Fetch the latest exchange rate from the API."""
        url = "https://criptoya.com/api/usdt/ars"
        timeout: int = int(polling_rate * 0.8)  # 80% of the polling rate
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        return data.get("buenbit", {})

    def store(self, source: str, buy: float, sell: float, current_time: datetime) -> None:
        """Store the exchange rate somewhere."""
        self._insert_entry_in_database(current_time=current_time, source=source, buy=buy, sell=sell)

    def _insert_entry_in_database(self, current_time: datetime, source: str, buy: float, sell: float) -> None:
        """Insert the fetched exchange rate into a database."""
        with DatabaseSession(engine=self.database_engine) as db_service:
            db_service.add(Entry(datetime=current_time, source=source, buy=buy, sell=sell))


def main() -> None:
    """Main function that starts the poller service"""
    project_folder: Path = Path(__file__).resolve().parent.parent
    assert project_folder.name == "crypto_tracking", "Project folder is not named 'crypto_tracking'"

    configure_logger(project_folder=project_folder)

    db_engine: Engine = DatabaseService(project_folder=project_folder).start()
    polling_rate: int = 60
    poller(project_folder=project_folder, db_engine=db_engine, polling_rate=polling_rate)


if __name__ == "__main__":
    main()
