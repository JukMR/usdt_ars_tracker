import csv
from datetime import datetime
from pathlib import Path


def store_exchange_rate_to_csv(buy: float, sell: float, data_folder: Path) -> None:
    """Store the fetched exchange rate into a CSV file."""
    exchange_rate_file: Path = data_folder / "exchange_rates.csv"

    with open(exchange_rate_file, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.now(), "buenbit", buy, sell])


def check_csv_header(data_folder: Path) -> None:
    output_file = data_folder / "exchange_rates.csv"
    try:
        with open(output_file, "x", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp", "source", "buy", "sell"])

    except FileExistsError:
        pass  # File already exists, no need to add headers
