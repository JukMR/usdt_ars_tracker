"""Main module that fetches and stores the exchange rate from Buenbit."""

import csv
import time
from datetime import datetime
from typing import Any, Dict, NoReturn

import requests
import schedule


def fetch_exchange_rate() -> Dict[str, Any]:
    """Fetch the latest exchange rate from the API."""
    url = "https://criptoya.com/api/usdt/ars"
    response = requests.get(url, timeout=5)
    data = response.json()
    return data.get("buenbit", {})


def store_exchange_rate_to_csv(buy: float, sell: float) -> None:
    """Store the fetched exchange rate into a CSV file."""
    with open("exchange_rates.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.now(), "buenbit", buy, sell])


def job() -> None:
    """The scheduled job that fetches and stores the exchange rate."""
    rate_data = fetch_exchange_rate()
    if rate_data:
        buy = float(rate_data["totalAsk"])
        sell = float(rate_data["totalBid"])

        store_exchange_rate_to_csv(buy=buy, sell=sell)
        print(f"Stored new buy: {rate_data['totalAsk']} at {datetime.now()}")
        print(f"Stored new sell: {rate_data['totalBid']} at {datetime.now()}")


def check_csv_header() -> None:
    try:
        with open("exchange_rates.csv", "x", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Source", "Buy", "Sell"])
    except FileExistsError:
        pass  # File already exists, no need to add headers


def run() -> None:
    schedule.run_pending()
    time.sleep(1)


def main() -> NoReturn:
    """Main function that starts the exchange rate tracking app."""

    # Check if the CSV needs headers and add them if it does
    check_csv_header()

    schedule.every(30).seconds.do(job)

    print("Starting exchange rate tracking app...")
    while True:
        try:
            run()
        except Exception as exc:  # pylint: disable=broad-except
            print(f"An error occurred: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()
