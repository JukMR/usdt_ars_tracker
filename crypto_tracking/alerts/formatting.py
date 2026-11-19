"""Human-readable alert text formatting."""

from __future__ import annotations

from crypto_tracking.domain import Operator, ensure_utc
from crypto_tracking.storage.models import AlertEventRow, AlertRow

OPERATOR_PHRASES: dict[str, str] = {
    Operator.LESS_THAN.value: "is below",
    Operator.LESS_THAN_OR_EQUAL.value: "is at or below",
    Operator.EQUAL.value: "is equal to",
    Operator.GREATER_THAN.value: "is above",
    Operator.GREATER_THAN_OR_EQUAL.value: "is at or above",
}


def format_number(value: float | None) -> str:
    if value is None:
        return "—"

    absolute = abs(value)
    if absolute >= 1000:
        return f"{value:,.2f}"
    if absolute >= 1:
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return f"{value:,.8f}".rstrip("0").rstrip(".")


def pair_label(asset: str, quote_currency: str) -> str:
    return f"{asset.upper()}/{quote_currency.upper()}"


def condition_text(alert: AlertRow) -> str:
    return f"{alert.metric} {alert.operator} {format_number(alert.threshold)}"


def alert_title(alert: AlertRow) -> str:
    return f"{pair_label(alert.asset, alert.quote_currency)} {alert.metric} alert"


def alert_message(alert: AlertRow, value: float, source: str, triggered_at) -> str:
    phrase = OPERATOR_PHRASES.get(alert.operator, f"{alert.operator}")
    label = alert.label or "Threshold"
    return (
        f"{label}: {pair_label(alert.asset, alert.quote_currency)} {alert.metric} "
        f"{phrase} {format_number(alert.threshold)} — current value {format_number(value)} "
        f"(source: {source}) at {ensure_utc(triggered_at).strftime('%Y-%m-%d %H:%M:%S UTC')}."
    )


def event_text(event: AlertEventRow) -> str:
    phrase = OPERATOR_PHRASES.get(event.operator, event.operator)
    return (
        f"{pair_label(event.asset, event.quote_currency)} {event.metric} "
        f"{phrase} {format_number(event.threshold)} — value {format_number(event.value)}"
    )
