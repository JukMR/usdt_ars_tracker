from __future__ import annotations

from datetime import datetime, timedelta

from crypto_tracking.alerts.engine import AlertEngine
from crypto_tracking.domain import Notification, Quote, utcnow
from crypto_tracking.notifiers.base import Notifier
from crypto_tracking.notifiers.registry import NotifierRegistry


class RecordingNotifier(Notifier):
    channel = "recording"

    def __init__(self):
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


class FailingNotifier(Notifier):
    channel = "broken"

    def send(self, notification: Notification) -> None:
        raise RuntimeError("delivery exploded")


def _seed(prices, price: float, *, source: str = "test", at: datetime | None = None) -> None:
    prices.add_quotes(
        [
            Quote(
                asset="BTC",
                quote_currency="USDT",
                source=source,
                price=price,
                bid=price - 1,
                ask=price + 1,
                timestamp=at or utcnow(),
            )
        ]
    )


def test_triggers_once_and_records_delivery(repos):
    prices, alerts = repos
    recording = RecordingNotifier()
    registry = NotifierRegistry()
    registry.register(recording)
    engine = AlertEngine(alerts, prices, registry)

    _seed(prices, 100)
    alert = alerts.create_alert(
        asset="BTC",
        quote_currency="USDT",
        metric="price",
        operator=">",
        threshold=50,
        channels=["recording"],
    )

    now = utcnow()
    events = engine.evaluate(now=now)
    assert len(events) == 1
    assert len(recording.sent) == 1
    assert "BTC/USDT" in recording.sent[0].title

    assert engine.evaluate(now=now + timedelta(seconds=1)) == []

    deliveries = alerts.list_events()[0].deliveries
    assert len(deliveries) == 1
    assert deliveries[0].channel == "recording"
    assert deliveries[0].success is True
    assert alerts.get_alert(alert.id).last_triggered_at is not None


def test_rearms_after_condition_becomes_false(repos):
    prices, alerts = repos
    registry = NotifierRegistry()
    registry.register(RecordingNotifier())
    engine = AlertEngine(alerts, prices, registry)

    base = utcnow()
    _seed(prices, 100, at=base)
    alerts.create_alert(
        asset="BTC",
        quote_currency="USDT",
        metric="price",
        operator=">",
        threshold=50,
        channels=["recording"],
        cooldown_seconds=0,
    )

    assert len(engine.evaluate(now=base + timedelta(seconds=1))) == 1

    _seed(prices, 40, at=base + timedelta(seconds=2))
    assert engine.evaluate(now=base + timedelta(seconds=3)) == []

    _seed(prices, 100, at=base + timedelta(seconds=4))
    assert len(engine.evaluate(now=base + timedelta(seconds=5))) == 1


def test_cooldown_suppresses_rapid_rearm(repos):
    prices, alerts = repos
    registry = NotifierRegistry()
    registry.register(RecordingNotifier())
    engine = AlertEngine(alerts, prices, registry)

    base = utcnow()
    _seed(prices, 100, at=base)
    alerts.create_alert(
        asset="BTC",
        quote_currency="USDT",
        metric="price",
        operator=">",
        threshold=50,
        channels=["recording"],
        cooldown_seconds=3600,
    )

    assert len(engine.evaluate(now=base + timedelta(seconds=1))) == 1
    _seed(prices, 40, at=base + timedelta(seconds=2))
    engine.evaluate(now=base + timedelta(seconds=3))
    _seed(prices, 100, at=base + timedelta(seconds=4))

    # Re-armed, but still inside the cooldown window.
    assert engine.evaluate(now=base + timedelta(seconds=5)) == []


def test_repeat_mode_fires_again_after_cooldown(repos):
    prices, alerts = repos
    registry = NotifierRegistry()
    registry.register(RecordingNotifier())
    engine = AlertEngine(alerts, prices, registry)

    base = utcnow()
    _seed(prices, 100, at=base)
    alerts.create_alert(
        asset="BTC",
        quote_currency="USDT",
        metric="price",
        operator=">",
        threshold=50,
        channels=["recording"],
        cooldown_seconds=60,
        repeat=True,
    )

    assert len(engine.evaluate(now=base + timedelta(seconds=1))) == 1
    assert engine.evaluate(now=base + timedelta(seconds=30)) == []
    assert len(engine.evaluate(now=base + timedelta(seconds=62))) == 1


def test_one_channel_failure_does_not_block_others(repos):
    prices, alerts = repos
    recording = RecordingNotifier()
    registry = NotifierRegistry()
    registry.register(recording)
    registry.register(FailingNotifier())
    engine = AlertEngine(alerts, prices, registry)

    _seed(prices, 100)
    alerts.create_alert(
        asset="BTC",
        quote_currency="USDT",
        metric="price",
        operator=">",
        threshold=50,
        channels=["broken", "recording"],
    )

    events = engine.evaluate()
    assert len(events) == 1
    assert len(recording.sent) == 1

    statuses = {delivery.channel: delivery.success for delivery in alerts.list_events()[0].deliveries}
    assert statuses == {"broken": False, "recording": True}


def test_unknown_channel_is_recorded_as_failure(repos):
    prices, alerts = repos
    registry = NotifierRegistry()
    engine = AlertEngine(alerts, prices, registry)

    _seed(prices, 100)
    alerts.create_alert(
        asset="BTC", quote_currency="USDT", metric="price", operator=">", threshold=50, channels=["missing"]
    )

    assert len(engine.evaluate()) == 1
    delivery = alerts.list_events()[0].deliveries[0]
    assert delivery.channel == "missing"
    assert delivery.success is False
    assert "missing" in (delivery.error or "")


def test_no_price_means_no_event(repos):
    prices, alerts = repos
    registry = NotifierRegistry()
    engine = AlertEngine(alerts, prices, registry)

    alerts.create_alert(
        asset="BTC", quote_currency="USDT", metric="price", operator=">", threshold=50, channels=["log"]
    )
    assert engine.evaluate() == []


def test_source_specific_alert_uses_that_source(repos):
    prices, alerts = repos
    recording = RecordingNotifier()
    registry = NotifierRegistry()
    registry.register(recording)
    engine = AlertEngine(alerts, prices, registry)

    base = utcnow()
    _seed(prices, 100, source="venue-a", at=base)
    _seed(prices, 900, source="venue-b", at=base + timedelta(seconds=1))

    alerts.create_alert(
        asset="BTC",
        quote_currency="USDT",
        metric="price",
        operator=">",
        threshold=50,
        source="venue-b",
        channels=["recording"],
    )

    events = engine.evaluate(now=base + timedelta(seconds=2))
    assert len(events) == 1
    assert events[0].source == "venue-b"
    assert events[0].value == 900


def test_invalid_metric_is_skipped(repos):
    prices, alerts = repos
    registry = NotifierRegistry()
    registry.register(RecordingNotifier())
    engine = AlertEngine(alerts, prices, registry)

    _seed(prices, 100)
    alerts.create_alert(
        asset="BTC", quote_currency="USDT", metric="not-a-metric", operator=">", threshold=50, channels=["recording"]
    )

    assert engine.evaluate() == []


def test_alert_without_channels_still_records_event(repos):
    prices, alerts = repos
    registry = NotifierRegistry()
    engine = AlertEngine(alerts, prices, registry)

    _seed(prices, 100)
    alerts.create_alert(asset="BTC", quote_currency="USDT", metric="price", operator=">", threshold=50, channels=[])

    events = engine.evaluate()
    assert len(events) == 1
    assert alerts.list_events()[0].deliveries == []
