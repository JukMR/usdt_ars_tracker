"""Alert evaluation and delivery orchestration."""

from __future__ import annotations

import logging
from datetime import datetime

from crypto_tracking.alerts.formatting import alert_message, alert_title
from crypto_tracking.domain import Metric, Notification, Operator, ensure_utc, utcnow
from crypto_tracking.notifiers.registry import NotifierRegistry
from crypto_tracking.storage.models import AlertEventRow, AlertRow
from crypto_tracking.storage.repositories import AlertRepository, PriceRepository

logger = logging.getLogger(__name__)


class AlertEngine:
    """Evaluate stored alerts against the latest prices and deliver them.

    Semantics
    ---------
    - Edge-triggered by default: a threshold fires when the condition becomes
      true, not on every poll while it stays true.
    - When the condition becomes false the alert re-arms.
    - ``cooldown_seconds`` suppresses rapid re-firing.
    - With ``repeat=True`` the alert fires again every cooldown while the
      condition remains true.
    """

    def __init__(
        self,
        alerts: AlertRepository,
        prices: PriceRepository,
        notifiers: NotifierRegistry,
    ) -> None:
        self.alerts = alerts
        self.prices = prices
        self.notifiers = notifiers

    def evaluate(self, now: datetime | None = None) -> list[AlertEventRow]:
        """Check all enabled alerts once and return triggered events."""
        current_time = ensure_utc(now or utcnow())
        triggered: list[AlertEventRow] = []

        for alert in self.alerts.list_alerts(enabled_only=True):
            quote = self.prices.latest(alert.asset, alert.quote_currency, source=alert.source)
            if quote is None:
                logger.debug(
                    "No price available for %s/%s (source=%s); skipping alert %s",
                    alert.asset,
                    alert.quote_currency,
                    alert.source,
                    alert.id,
                )
                continue

            try:
                value = quote.value(Metric(alert.metric))
                operator = Operator(alert.operator)
            except ValueError:
                logger.error("Alert %s has an invalid metric or operator; skipping", alert.id)
                continue

            if value is None:
                logger.debug("Alert %s metric %s is unavailable; skipping", alert.id, alert.metric)
                continue

            condition = operator.compare(float(value), alert.threshold)
            if self._should_fire(alert, condition=condition, now=current_time):
                triggered.append(self._trigger(alert, value=float(value), source=quote.source, now=current_time))

            self.alerts.set_last_state(alert.id, condition)

        if triggered:
            logger.info("Triggered %d alert(s)", len(triggered))
        return triggered

    def _should_fire(self, alert: AlertRow, *, condition: bool, now: datetime) -> bool:
        if not condition:
            return False

        cooldown = max(0, alert.cooldown_seconds or 0)
        last_triggered = ensure_utc(alert.last_triggered_at) if alert.last_triggered_at else None
        cooldown_elapsed = last_triggered is None or (now - last_triggered).total_seconds() >= cooldown

        if alert.repeat:
            return cooldown_elapsed

        # Edge-triggered: only fire on a false -> true transition.
        if alert.last_state is True:
            return False
        return cooldown_elapsed

    def _trigger(self, alert: AlertRow, *, value: float, source: str, now: datetime) -> AlertEventRow:
        message = alert_message(alert, value=value, source=source, triggered_at=now)
        event = self.alerts.record_event(alert, value=value, source=source, message=message, triggered_at=now)
        self.alerts.mark_triggered(alert.id, now)

        notification = Notification(
            title=alert_title(alert),
            message=message,
            metadata={
                "alert_id": alert.id,
                "asset": alert.asset,
                "quote_currency": alert.quote_currency,
                "metric": alert.metric,
                "operator": alert.operator,
                "threshold": alert.threshold,
                "value": value,
                "source": source,
            },
        )

        channels = list(alert.channels or [])
        if not channels:
            logger.warning("Alert %s triggered but has no notification channels configured", alert.id)

        for channel in channels:
            self._deliver(event, channel, notification)

        return event

    def _deliver(self, event: AlertEventRow, channel: str, notification: Notification) -> None:
        try:
            notifier = self.notifiers.get(channel)
            notifier.send(notification)
        except Exception as exc:  # noqa: BLE001 - one channel must not block the others
            logger.error("Delivery via %s failed for event %s: %s", channel, event.id, exc)
            self._record_delivery(event.id, channel, success=False, error=str(exc))
        else:
            logger.info("Delivery via %s succeeded for event %s", channel, event.id)
            self._record_delivery(event.id, channel, success=True)

    def _record_delivery(self, event_id: int, channel: str, *, success: bool, error: str | None = None) -> None:
        try:
            self.alerts.record_delivery(event_id, channel, success=success, error=error)
        except Exception:  # pragma: no cover - history should never break delivery flow
            logger.exception("Could not record delivery for event %s", event_id)
