"""Binance public market-data provider."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import requests

from crypto_tracking.domain import Quote, utcnow
from crypto_tracking.providers.base import PriceProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.binance.com"
DEFAULT_QUOTE_SUFFIXES = (
    "USDT",
    "USDC",
    "FDUSD",
    "BUSD",
    "TUSD",
    "DAI",
    "BTC",
    "ETH",
    "BNB",
    "EUR",
    "TRY",
    "BRL",
    "ARS",
    "JPY",
)


class BinanceProvider(PriceProvider):
    """Fetch last price, bid, ask and volume from Binance's public REST API."""

    name = "binance"

    def __init__(
        self,
        symbols: list[str],
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.symbols = [symbol.upper() for symbol in symbols if symbol]
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self._markets = self._parse_markets(self.symbols)

    def pairs(self) -> list[tuple[str, str]]:
        return list(self._markets.values())

    def fetch(self) -> list[Quote]:
        if not self._markets:
            return []

        response = self._session.get(
            f"{self.base_url}/api/v3/ticker/24hr",
            params={"symbols": json.dumps(list(self._markets), separators=(",", ":"))},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            if "code" in payload:
                raise ValueError(f"Binance error: {payload.get('msg', payload)}")
            payload = [payload]

        quotes: list[Quote] = []
        for item in payload:
            symbol = str(item.get("symbol", "")).upper()
            market = self._markets.get(symbol)
            if market is None:
                continue

            try:
                price = float(item["lastPrice"])
            except (KeyError, TypeError, ValueError):
                logger.warning("Skipping Binance ticker without a valid lastPrice: %s", item)
                continue

            if price <= 0:
                continue

            timestamp = _timestamp_from_ms(item.get("closeTime"))
            quotes.append(
                Quote(
                    asset=market[0],
                    quote_currency=market[1],
                    source=self.name,
                    price=price,
                    bid=_optional_float(item.get("bidPrice")),
                    ask=_optional_float(item.get("askPrice")),
                    volume=_optional_float(item.get("quoteVolume")),
                    timestamp=timestamp,
                )
            )

        return quotes

    def _parse_markets(self, symbols: list[str]) -> dict[str, tuple[str, str]]:
        markets: dict[str, tuple[str, str]] = {}
        for symbol in symbols:
            parsed = split_symbol(symbol)
            if parsed is None:
                logger.warning("Could not infer asset/quote from Binance symbol: %s", symbol)
                continue
            markets[symbol] = parsed
        return markets


def split_symbol(symbol: str) -> tuple[str, str] | None:
    """Split a Binance symbol such as ``BTCUSDT`` into ``("BTC", "USDT")``."""
    symbol = symbol.upper()
    for suffix in DEFAULT_QUOTE_SUFFIXES:
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            return symbol[: -len(suffix)], suffix
    return None


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _timestamp_from_ms(value: object) -> datetime:
    if not isinstance(value, (int, float, str)):
        return utcnow()
    try:
        milliseconds = int(float(value))
    except (TypeError, ValueError):
        return utcnow()
    if milliseconds <= 0:
        return utcnow()
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
