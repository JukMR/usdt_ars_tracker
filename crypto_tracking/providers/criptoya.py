"""Criptoya provider for Argentine peso (ARS) rates."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import requests  # type: ignore[import-untyped]

from crypto_tracking.domain import Quote, utcnow
from crypto_tracking.providers.base import PriceProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://criptoya.com/api"


class CriptoyaProvider(PriceProvider):
    """Fetch exchange rates from criptoya.com.

    Criptoya aggregates several Argentine exchanges. The configured exchanges
    are selected from the response so the dashboard can show, for example,
    USDT/ARS on Buenbit without hard-coding a single venue.
    """

    name = "criptoya"

    def __init__(
        self,
        *,
        coin: str = "usdt",
        fiat: str = "ars",
        exchanges: list[str] | tuple[str, ...] = ("ripio",),
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.coin = coin.lower()
        self.fiat = fiat.lower()
        self.exchanges = [exchange.lower() for exchange in exchanges]
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()

    def pairs(self) -> list[tuple[str, str]]:
        return [(self.coin.upper(), self.fiat.upper())]

    def fetch(self) -> list[Quote]:
        response = self._session.get(
            f"{self.base_url}/{self.coin}/{self.fiat}",
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict):
            raise TypeError("Unexpected criptoya response: expected an object")

        # An empty exchange list means "every venue criptoya returns".
        exchanges = self.exchanges or [str(name) for name in payload]
        quotes: list[Quote] = []
        for exchange in exchanges:
            data = payload.get(exchange)
            if not isinstance(data, dict):
                logger.warning("Exchange %s not present in criptoya response", exchange)
                continue

            bid = _first_float(data, "totalBid", "bid")
            ask = _first_float(data, "totalAsk", "ask")
            if bid is None and ask is None:
                logger.warning("Exchange %s returned no usable bid/ask values", exchange)
                continue

            price: float | None
            if bid is not None and ask is not None:
                price = (bid + ask) / 2
            else:
                price = ask if ask is not None else bid
            if price is None or price <= 0:
                continue

            quotes.append(
                Quote(
                    asset=self.coin.upper(),
                    quote_currency=self.fiat.upper(),
                    source=f"criptoya:{exchange}",
                    price=price,
                    bid=bid,
                    ask=ask,
                    timestamp=_timestamp_from_seconds(data.get("time")),
                )
            )

        return quotes


def _first_float(data: dict[str, object], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        try:
            result = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if result > 0:
            return result
    return None


def _timestamp_from_seconds(value: object) -> datetime:
    if not isinstance(value, (int, float, str)):
        return utcnow()
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return utcnow()
    if seconds <= 0:
        return utcnow()
    return datetime.fromtimestamp(seconds, tz=UTC)
