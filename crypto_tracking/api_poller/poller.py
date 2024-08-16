"""Main module that fetches and stores the exchange rate from Buenbit."""

from typing import Any

import requests


def fetch_exchange_rate(polling_rate: int) -> dict[str, Any]:
    """Fetch the latest exchange rate from the API."""
    url = "https://criptoya.com/api/usdt/ars"
    timeout: int = int(polling_rate * 0.8)  # 80% of the polling rate
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    return data.get("buenbit", {})
