"""Price polling loop."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from crypto_tracking.domain import Quote
from crypto_tracking.providers.base import PriceProvider
from crypto_tracking.storage.repositories import PriceRepository

logger = logging.getLogger(__name__)

CycleCallback = Callable[[], object]


class Poller:
    """Fetch quotes from every provider and persist them.

    ``on_cycle`` runs after each polling round; the CLI uses it to evaluate
    alerts immediately after new prices arrive.
    """

    def __init__(
        self,
        providers: list[PriceProvider],
        prices: PriceRepository,
        interval_seconds: int = 60,
        *,
        on_cycle: CycleCallback | None = None,
    ) -> None:
        self.providers = providers
        self.prices = prices
        self.interval_seconds = max(5, int(interval_seconds))
        self.on_cycle = on_cycle

    def poll_once(self) -> list[Quote]:
        """Poll every provider once and store the returned quotes."""
        all_quotes: list[Quote] = []

        for provider in self.providers:
            try:
                quotes = provider.fetch()
            except Exception:
                logger.exception("Provider %s failed", provider.name)
                continue

            if not quotes:
                logger.warning("Provider %s returned no quotes", provider.name)
                continue

            inserted = self.prices.add_quotes(quotes)
            logger.info(
                "Provider %s returned %d quote(s), %d new row(s) stored",
                provider.name,
                len(quotes),
                inserted,
            )
            all_quotes.extend(quotes)

        return all_quotes

    def run(self, stop_event: threading.Event | None = None) -> None:
        """Run until ``stop_event`` is set (or forever when omitted)."""
        stop_event = stop_event or threading.Event()
        logger.info(
            "Poller started with %d provider(s); interval=%ss",
            len(self.providers),
            self.interval_seconds,
        )

        while not stop_event.is_set():
            self.poll_once()
            if self.on_cycle is not None:
                try:
                    self.on_cycle()
                except Exception:
                    logger.exception("Post-poll callback failed")

            if stop_event.wait(self.interval_seconds):
                break

        logger.info("Poller stopped")
