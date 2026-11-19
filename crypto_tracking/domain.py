"""Core domain objects shared by providers, storage, alerts and the web app.

The goal of this module is to keep the rest of the codebase free of
provider-specific or database-specific structures. Prices enter the system as
:class:`Quote` objects and alerts are described with plain enums and numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

RANGE_DELTAS: dict[str, timedelta | None] = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalise a datetime to timezone-aware UTC.

    SQLite does not preserve timezone information, so values read back from the
    database are often naive. Treat those as UTC instead of guessing the local
    timezone.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def range_since(range_key: str, now: datetime | None = None) -> datetime | None:
    """Translate a dashboard range key into a lower timestamp bound."""
    try:
        delta = RANGE_DELTAS[range_key]
    except KeyError as exc:
        raise ValueError(f"Unsupported range: {range_key}") from exc

    if delta is None:
        return None
    return ensure_utc(now or utcnow()) - delta


class Metric(StrEnum):
    """The price field an alert is evaluated against."""

    PRICE = "price"
    BID = "bid"
    ASK = "ask"


class Operator(StrEnum):
    """Comparison operators supported by alerts."""

    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="

    def compare(self, value: float, threshold: float) -> bool:
        """Return whether ``value`` satisfies this operator against ``threshold``."""
        match self:
            case Operator.LESS_THAN:
                return value < threshold
            case Operator.LESS_THAN_OR_EQUAL:
                return value <= threshold
            case Operator.EQUAL:
                return value == threshold
            case Operator.GREATER_THAN:
                return value > threshold
            case Operator.GREATER_THAN_OR_EQUAL:
                return value >= threshold
            case _:  # pragma: no cover - exhaustive enum
                raise ValueError(f"Unsupported operator: {self}")


@dataclass(frozen=True, slots=True)
class Quote:
    """A single price observation for an asset on a venue."""

    asset: str
    quote_currency: str
    source: str
    price: float
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    timestamp: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", self.asset.upper())
        object.__setattr__(self, "quote_currency", self.quote_currency.upper())
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))

    @property
    def pair(self) -> str:
        return f"{self.asset}/{self.quote_currency}"

    def value(self, metric: Metric | str) -> float | None:
        """Return the requested metric for this quote."""
        field_name = metric.value if isinstance(metric, Metric) else str(metric)
        if field_name not in {m.value for m in Metric}:
            raise ValueError(f"Unsupported metric: {metric}")
        return getattr(self, field_name)


@dataclass(frozen=True, slots=True)
class PriceStats:
    """Aggregate statistics for a pair over a time window."""

    count: int
    minimum: float | None
    maximum: float | None
    average: float | None
    first: float | None
    last: float | None

    @property
    def change(self) -> float | None:
        if self.first is None or self.last is None:
            return None
        return self.last - self.first

    @property
    def change_percent(self) -> float | None:
        if self.first is None or self.last is None or self.first == 0:
            return None
        return (self.last - self.first) / self.first * 100


@dataclass(frozen=True, slots=True)
class Notification:
    """Channel-agnostic message handed to a notifier."""

    title: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
