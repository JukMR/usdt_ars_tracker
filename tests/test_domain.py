from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from crypto_tracking.domain import Metric, Operator, PriceStats, Quote, ensure_utc, range_since, utcnow


@pytest.mark.parametrize(
    ("operator", "value", "threshold", "expected"),
    [
        (Operator.LESS_THAN, 9.0, 10.0, True),
        (Operator.LESS_THAN, 10.0, 10.0, False),
        (Operator.LESS_THAN_OR_EQUAL, 10.0, 10.0, True),
        (Operator.EQUAL, 10.0, 10.0, True),
        (Operator.EQUAL, 10.1, 10.0, False),
        (Operator.GREATER_THAN, 11.0, 10.0, True),
        (Operator.GREATER_THAN, 10.0, 10.0, False),
        (Operator.GREATER_THAN_OR_EQUAL, 10.0, 10.0, True),
    ],
)
def test_operator_compare(operator, value, threshold, expected):
    assert operator.compare(value, threshold) is expected


def test_quote_normalises_values_and_timezone():
    naive = datetime(2024, 1, 1, 12, 0, 0)
    quote = Quote(asset="btc", quote_currency="usdt", source="test", price=1.0, timestamp=naive)

    assert quote.asset == "BTC"
    assert quote.quote_currency == "USDT"
    assert quote.pair == "BTC/USDT"
    assert quote.timestamp.tzinfo == UTC


def test_quote_value_metric():
    quote = Quote("BTC", "USDT", "test", price=100.0, bid=99.0, ask=101.0)
    assert quote.value(Metric.PRICE) == 100.0
    assert quote.value("bid") == 99.0
    assert quote.value("ask") == 101.0

    with pytest.raises(ValueError):
        quote.value("volume")


def test_ensure_utc_treats_naive_as_utc():
    naive = datetime(2024, 1, 1, 12, 0, 0)
    assert ensure_utc(naive).tzinfo == UTC

    aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert ensure_utc(aware).hour == 15


def test_range_since():
    now = utcnow()
    assert range_since("24h", now) == now - timedelta(hours=24)
    assert range_since("all", now) is None

    with pytest.raises(ValueError):
        range_since("99y", now)


def test_price_stats_change():
    stats = PriceStats(count=10, minimum=90.0, maximum=110.0, average=100.0, first=95.0, last=105.0)
    assert stats.change == 10.0
    assert round(stats.change_percent or 0, 4) == round(10 / 95 * 100, 4)

    empty = PriceStats(count=0, minimum=None, maximum=None, average=None, first=None, last=None)
    assert empty.change is None
    assert empty.change_percent is None

    zero = PriceStats(count=1, minimum=0.0, maximum=0.0, average=0.0, first=0.0, last=1.0)
    assert zero.change_percent is None
