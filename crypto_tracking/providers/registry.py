"""Build the active price providers from configuration."""

from __future__ import annotations

import logging

from crypto_tracking.config import Settings
from crypto_tracking.providers.base import PriceProvider
from crypto_tracking.providers.binance import BinanceProvider
from crypto_tracking.providers.coingecko import CoinGeckoProvider
from crypto_tracking.providers.criptoya import CriptoyaProvider

logger = logging.getLogger(__name__)


def build_providers(settings: Settings) -> list[PriceProvider]:
    """Instantiate every enabled provider."""
    providers: list[PriceProvider] = []

    if settings.binance.enabled and settings.binance.symbols:
        providers.append(BinanceProvider(symbols=settings.binance.symbols))

    if settings.criptoya.enabled:
        providers.append(
            CriptoyaProvider(
                coin=settings.criptoya.coin,
                fiat=settings.criptoya.fiat,
                exchanges=settings.criptoya.exchanges,
            )
        )

    if settings.coingecko.enabled and settings.coingecko.assets:
        providers.append(
            CoinGeckoProvider(
                assets=settings.coingecko.assets,
                quote_currency=settings.coingecko.quote_currency,
            )
        )

    if not providers:
        logger.warning("No price providers are enabled; the poller will not fetch anything.")

    return providers


def configured_pairs(settings: Settings) -> list[tuple[str, str]]:
    """Return the pairs the configured providers are expected to produce."""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for provider in build_providers(settings):
        for pair in provider.pairs():
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
    return pairs
