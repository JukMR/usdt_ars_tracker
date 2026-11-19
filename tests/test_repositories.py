from __future__ import annotations

from datetime import timedelta

from crypto_tracking.domain import Quote, utcnow
from crypto_tracking.storage.repositories import AlertRepository, PriceRepository


def _quote(asset="BTC", quote="USDT", source="test", price=100.0, offset_minutes=0):
    return Quote(
        asset=asset,
        quote_currency=quote,
        source=source,
        price=price,
        bid=price - 1,
        ask=price + 1,
        timestamp=utcnow() + timedelta(minutes=offset_minutes),
    )


def test_add_quotes_deduplicates(db):
    prices = PriceRepository(db)
    first = _quote()
    assert prices.add_quotes([first]) == 1
    assert prices.add_quotes([first]) == 0
    assert prices.count() == 1


def test_latest_and_latest_all(repos):
    prices, _ = repos
    prices.add_quotes(
        [
            _quote(source="venue-a", price=100, offset_minutes=-2),
            _quote(source="venue-a", price=101, offset_minutes=-1),
            _quote(source="venue-b", price=200, offset_minutes=-3),
        ]
    )

    latest = prices.latest("BTC", "USDT")
    assert latest is not None
    assert latest.price == 101

    latest_a = prices.latest("BTC", "USDT", source="venue-a")
    assert latest_a is not None
    assert latest_a.source == "venue-a"

    all_latest = prices.latest_all()
    assert len(all_latest) == 2
    assert {quote.source for quote in all_latest} == {"venue-a", "venue-b"}


def test_history_and_stats(repos):
    prices, _ = repos
    prices.add_quotes([_quote(price=value, offset_minutes=index) for index, value in enumerate([100, 110, 90, 120])])

    history = prices.history("BTC", "USDT")
    assert [quote.price for quote in history] == [100, 110, 90, 120]

    limited = prices.history("BTC", "USDT", limit=2)
    assert [quote.price for quote in limited] == [90, 120]

    stats = prices.stats("BTC", "USDT")
    assert stats.count == 4
    assert stats.minimum == 90
    assert stats.maximum == 120
    assert stats.first == 100
    assert stats.last == 120

    future = utcnow() + timedelta(days=1)
    empty = prices.stats("BTC", "USDT", since=future)
    assert empty.count == 0
    assert empty.minimum is None


def test_history_since_filters(repos):
    prices, _ = repos
    prices.add_quotes([_quote(price=value, offset_minutes=index) for index, value in enumerate([100, 110, 120])])

    history = prices.history("BTC", "USDT", since=utcnow() + timedelta(minutes=1, seconds=30))
    assert [quote.price for quote in history] == [120]


def test_pairs(repos):
    prices, _ = repos
    prices.add_quotes([_quote(asset="BTC", price=100), _quote(asset="ETH", price=200)])

    pairs = prices.pairs()
    assert len(pairs) == 2
    assert {row["asset"] for row in pairs} == {"BTC", "ETH"}
    assert all(row["count"] == 1 for row in pairs)


def test_alert_crud(repos):
    _, alerts = repos
    created = alerts.create_alert(
        asset="btc",
        quote_currency="usdt",
        metric="price",
        operator=">",
        threshold=70000,
        channels=["log", "log"],
        cooldown_seconds=-5,
        label="breakout",
    )

    assert created.id is not None
    assert created.asset == "BTC"
    assert created.quote_currency == "USDT"
    assert created.channels == ["log"]
    assert created.cooldown_seconds == 0

    listed = alerts.list_alerts()
    assert len(listed) == 1
    assert alerts.count_alerts() == 1

    updated = alerts.update_alert(created.id, {"threshold": 80000, "label": ""})
    assert updated is not None
    assert updated.threshold == 80000
    assert updated.label is None

    alerts.set_last_state(created.id, True)
    assert alerts.get_alert(created.id).last_state is True
    alerts.update_alert(created.id, {"operator": "<"})
    assert alerts.get_alert(created.id).last_state is None

    alerts.set_last_state(created.id, True)
    alerts.update_alert(created.id, {"enabled": False})
    alerts.update_alert(created.id, {"enabled": True})
    assert alerts.get_alert(created.id).last_state is None

    assert alerts.delete_alert(created.id) is True
    assert alerts.delete_alert(created.id) is False
    assert alerts.count_alerts() == 0


def test_delete_all_alerts(repos):
    _, alerts = repos
    for threshold in (1, 2, 3):
        alerts.create_alert(asset="BTC", quote_currency="USDT", metric="price", operator=">", threshold=threshold)

    assert alerts.delete_all_alerts() == 3
    assert alerts.count_alerts() == 0


def test_event_and_delivery_history(repos):
    _, alerts = repos
    alert = alerts.create_alert(
        asset="BTC", quote_currency="USDT", metric="price", operator=">", threshold=100, channels=["log"]
    )

    event = alerts.record_event(alert, value=101, source="test", message="triggered")
    alerts.record_delivery(event.id, "log", success=True)
    alerts.record_delivery(event.id, "email", success=False, error="smtp down")

    events = alerts.list_events()
    assert len(events) == 1
    assert events[0].id == event.id
    assert events[0].message == "triggered"
    assert [delivery.channel for delivery in events[0].deliveries] == ["log", "email"]
    assert events[0].deliveries[1].error == "smtp down"


def test_event_survives_alert_deletion(repos):
    _, alerts = repos
    alert = alerts.create_alert(asset="BTC", quote_currency="USDT", metric="price", operator=">", threshold=100)
    event = alerts.record_event(alert, value=101, source="test", message="triggered")

    alerts.delete_alert(alert.id)

    events = alerts.list_events()
    assert len(events) == 1
    assert events[0].id == event.id
    assert events[0].alert_id is None


def test_alert_repository_is_independent_of_price_repository(db):
    # Both repositories share the same database but own separate concerns.
    prices = PriceRepository(db)
    alerts = AlertRepository(db)
    assert prices.count() == 0
    assert alerts.count_alerts() == 0
