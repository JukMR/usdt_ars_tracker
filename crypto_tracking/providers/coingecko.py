"""CoinGecko provider for global USD prices.

CoinGecko is a useful fallback when an exchange API is unavailable. It does not
provide bid/ask values, only a last price.
"""

from __future__ import annotations

import logging

import requests  # type: ignore[import-untyped]

from crypto_tracking.domain import Quote, utcnow
from crypto_tracking.providers.base import PriceProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoProvider(PriceProvider):
    name = "coingecko"

    def __init__(
        self,
        *,
        assets: dict[str, str],
        quote_currency: str = "USD",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.assets = {coin_id.lower(): symbol.upper() for coin_id, symbol in assets.items()}
        self.quote_currency = quote_currency.upper()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()

    def pairs(self) -> list[tuple[str, str]]:
        return [(symbol, self.quote_currency) for symbol in self.assets.values()]

    def fetch(self) -> list[Quote]:
        if not self.assets:
            return []

        response = self._session.get(
            f"{self.base_url}/simple/price",
            params={
                "ids": ",".join(self.assets),
                "vs_currencies": self.quote_currency.lower(),
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict):
            raise TypeError("Unexpected CoinGecko response: expected an object")

        quotes: list[Quote] = []
        for coin_id, symbol in self.assets.items():
            data = payload.get(coin_id)
            if not isinstance(data, dict):
                logger.warning("CoinGecko did not return data for %s", coin_id)
                continue

            value = data.get(self.quote_currency.lower())
            try:
                price = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                logger.warning("CoinGecko returned no %s price for %s", self.quote_currency, coin_id)
                continue

            if price <= 0:
                continue

            quotes.append(
                Quote(
                    asset=symbol,
                    quote_currency=self.quote_currency,
                    source=self.name,
                    price=price,
                    timestamp=utcnow(),
                )
            )

        return quotes
