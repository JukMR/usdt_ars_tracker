"""Main module that fetches and stores the exchange rate from Buenbit."""

import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, NoReturn

import requests
import schedule
from logging_config import configure_logger, logger


def fetch_exchange_rate(polling_rate: int) -> Dict[str, Any]:
    """Fetch the latest exchange rate from the API."""
    url = "https://criptoya.com/api/usdt/ars"
    timeout: int = int(polling_rate * 0.8)  # 80% of the polling rate
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    return data.get("buenbit", {})


def store_exchange_rate_to_csv(buy: float, sell: float, data_folder: Path) -> None:
    """Store the fetched exchange rate into a CSV file."""
    exchange_rate_file: Path = data_folder / "exchange_rates.csv"

    with open(exchange_rate_file, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.now(), "buenbit", buy, sell])


def job(polling_rate: int, data_folder: Path) -> None:
    """The scheduled job that fetches and stores the exchange rate."""
    logger.info("Fetching exchange rate...")
    rate_data: dict[str, Any] = fetch_exchange_rate(polling_rate=polling_rate)
    if rate_data:
        buy = float(rate_data["totalAsk"])
        sell = float(rate_data["totalBid"])

        store_exchange_rate_to_csv(buy=buy, sell=sell, data_folder=data_folder)
        logger.info(f"Stored new buy: {rate_data['totalAsk']} at {datetime.now()}")
        logger.info(f"Stored new sell: {rate_data['totalBid']} at {datetime.now()}")


def check_csv_header(data_folder: Path) -> None:
    output_file = data_folder / "exchange_rates.csv"
    try:
        with open(output_file, "x", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp", "source", "buy", "sell"])

    except FileExistsError:
        pass  # File already exists, no need to add headers


def main() -> NoReturn:
    """Main function that starts the exchange rate tracking app."""

    # Configure project folders
    project_folder: Path = Path(__file__).resolve().parent
    assert project_folder.name == "crypto_tracking", "Project folder is not named 'crypto_tracking'"

    data_folder: Path = project_folder / "data"
    data_folder.mkdir(exist_ok=True)

    # Configure logger
    configure_logger(project_folder=project_folder)

    # Check if the CSV needs headers and add them if it does
    check_csv_header(data_folder=data_folder)

    # Main code

    polling_rate: int = 60
    schedule.every(polling_rate).seconds.do(job, polling_rate=polling_rate, data_folder=data_folder)

    logger.info("Starting exchange rate tracking app...")

    while True:
        time.sleep(5)
        try:
            schedule.run_pending()

        except Exception as exc:  # pylint: disable=broad-except
            logger.info(f"An error occurred: {exc}")


if __name__ == "__main__":
    main()
