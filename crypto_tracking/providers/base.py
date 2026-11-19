"""Price provider abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from crypto_tracking.domain import Quote


class PriceProvider(ABC):
    """A source of price quotes.

    Providers are deliberately small: fetch a batch of quotes and return them.
    Storage, alert evaluation and notification happen elsewhere, which makes it
    easy to add a new exchange or API later.
    """

    name: ClassVar[str]

    @abstractmethod
    def fetch(self) -> list[Quote]:
        """Fetch the latest quotes from the provider."""

    @abstractmethod
    def pairs(self) -> list[tuple[str, str]]:
        """Return the (asset, quote_currency) pairs this provider is configured for."""
