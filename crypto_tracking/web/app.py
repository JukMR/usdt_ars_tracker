"""Flask application: JSON API, dashboard and legacy endpoints."""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from flask import Flask, Response, jsonify, redirect, render_template, request
from flask.typing import ResponseReturnValue

from crypto_tracking.alerts.engine import AlertEngine
from crypto_tracking.alerts.formatting import condition_text
from crypto_tracking.config import Settings
from crypto_tracking.domain import (
    RANGE_DELTAS,
    Metric,
    Operator,
    PriceStats,
    Quote,
    ensure_utc,
    range_since,
    utcnow,
)
from crypto_tracking.notifiers.registry import NotifierRegistry
from crypto_tracking.providers.registry import configured_pairs
from crypto_tracking.storage.models import AlertEventRow, AlertRow, DeliveryRow
from crypto_tracking.storage.repositories import AlertRepository, PriceRepository


def create_app(
    *,
    settings: Settings,
    prices: PriceRepository,
    alerts: AlertRepository,
    engine: AlertEngine,
    notifiers: NotifierRegistry,
) -> Flask:
    """Create the dashboard/API application with explicit dependencies."""
    app = Flask(__name__)
    app.json.sort_keys = False  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @app.get("/")
    def dashboard() -> ResponseReturnValue:
        return render_template(
            "dashboard.html",
            refresh_seconds=settings.dashboard_refresh_seconds,
        )

    @app.get("/alerts")
    def legacy_alerts_page() -> ResponseReturnValue:
        return redirect("/#alerts")

    @app.get("/threshold")
    def legacy_threshold_page() -> ResponseReturnValue:
        return redirect("/#alerts")

    # ------------------------------------------------------------------
    # Configuration / health
    # ------------------------------------------------------------------
    @app.get("/api/health")
    def api_health() -> ResponseReturnValue:
        return jsonify(
            {
                "status": "ok",
                "time": _iso(utcnow()),
                "prices": prices.count(),
                "alerts": alerts.count_alerts(),
                "events": alerts.count_events(),
            }
        )

    @app.get("/api/config")
    def api_config() -> ResponseReturnValue:
        return jsonify(
            {
                "refresh_seconds": settings.dashboard_refresh_seconds,
                "ranges": list(RANGE_DELTAS),
                "providers": _enabled_provider_names(settings),
                "pairs": _all_pairs(settings, prices),
                "notifiers": notifiers.describe(),
                "default_channels": settings.default_channels,
                "poll_interval_seconds": settings.poll_interval_seconds,
            }
        )

    @app.get("/api/notifiers")
    def api_notifiers() -> ResponseReturnValue:
        return jsonify(
            {
                "data": notifiers.describe(),
                "default_channels": settings.default_channels,
            }
        )

    # ------------------------------------------------------------------
    # Prices
    # ------------------------------------------------------------------
    @app.get("/api/overview")
    def api_overview() -> ResponseReturnValue:
        range_key, since, error = _range_from_request()
        if error is not None:
            return error

        return jsonify(
            {
                "generated_at": _iso(utcnow()),
                "range": range_key,
                "pairs": [_pair_overview(prices, asset, quote, since) for asset, quote in _data_pairs(prices)],
            }
        )

    @app.get("/api/prices/latest")
    def api_latest_prices() -> ResponseReturnValue:
        quotes = prices.latest_all()
        return jsonify({"data": [_quote_to_dict(quote) for quote in quotes]})

    @app.get("/api/prices/history")
    def api_price_history() -> ResponseReturnValue:
        asset = (request.args.get("asset") or "").strip().upper()
        quote = (request.args.get("quote_currency") or request.args.get("quote") or "").strip().upper()
        if not asset or not quote:
            return _bad_request("asset and quote_currency are required")

        range_key, since, error = _range_from_request()
        if error is not None:
            return error

        source = (request.args.get("source") or "").strip() or None
        max_points = _clamp_int(request.args.get("max_points"), default=600, minimum=50, maximum=5000)

        quotes = prices.history(asset, quote, since=since, source=source, limit=20000)
        points = _downsample(quotes, max_points)

        return jsonify(
            {
                "asset": asset,
                "quote_currency": quote,
                "pair": f"{asset}/{quote}",
                "range": range_key,
                "points": points,
            }
        )

    @app.get("/api/prices/stats")
    def api_price_stats() -> ResponseReturnValue:
        range_key, since, error = _range_from_request()
        if error is not None:
            return error

        asset = (request.args.get("asset") or "").strip().upper()
        quote = (request.args.get("quote_currency") or request.args.get("quote") or "").strip().upper()
        if asset and quote:
            stats = prices.stats(asset, quote, since)
            return jsonify(
                {"asset": asset, "quote_currency": quote, "range": range_key, "stats": _stats_to_dict(stats)}
            )

        return jsonify(
            {
                "range": range_key,
                "pairs": [
                    {
                        "asset": pair_asset,
                        "quote_currency": pair_quote,
                        "stats": _stats_to_dict(prices.stats(pair_asset, pair_quote, since)),
                    }
                    for pair_asset, pair_quote in _data_pairs(prices)
                ],
            }
        )

    @app.get("/api/prices/export.csv")
    def api_export_prices() -> ResponseReturnValue:
        asset = (request.args.get("asset") or "").strip().upper()
        quote = (request.args.get("quote_currency") or request.args.get("quote") or "").strip().upper()
        _, since, error = _range_from_request()
        if error is not None:
            return error

        if asset and quote:
            pairs_to_export = [(asset, quote)]
        else:
            pairs_to_export = _data_pairs(prices)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "asset", "quote_currency", "source", "price", "bid", "ask", "volume"])
        for pair_asset, pair_quote in pairs_to_export:
            for quote_row in prices.history(pair_asset, pair_quote, since=since, limit=None):
                writer.writerow(
                    [
                        _iso(quote_row.timestamp),
                        quote_row.asset,
                        quote_row.quote_currency,
                        quote_row.source,
                        quote_row.price,
                        quote_row.bid if quote_row.bid is not None else "",
                        quote_row.ask if quote_row.ask is not None else "",
                        quote_row.volume if quote_row.volume is not None else "",
                    ]
                )

        filename = f"crypto_prices_{utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------
    @app.get("/api/alerts")
    def api_list_alerts() -> ResponseReturnValue:
        return jsonify({"data": [_alert_to_dict(alert) for alert in alerts.list_alerts()]})

    @app.post("/api/alerts")
    def api_create_alert() -> ResponseReturnValue:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return _bad_request("Expected a JSON object")

        try:
            changes = _alert_changes_from_payload(data, settings=settings, notifiers=notifiers, partial=False)
        except ValueError as exc:
            return _bad_request(str(exc))

        row = alerts.create_alert(
            asset=changes["asset"],
            quote_currency=changes["quote_currency"],
            metric=changes["metric"],
            operator=changes["operator"],
            threshold=changes["threshold"],
            source=changes.get("source"),
            channels=changes["channels"],
            cooldown_seconds=changes["cooldown_seconds"],
            repeat=changes["repeat"],
            enabled=changes["enabled"],
            label=changes.get("label"),
        )
        return jsonify({"data": _alert_to_dict(row)}), 201

    @app.patch("/api/alerts/<int:alert_id>")
    def api_update_alert(alert_id: int) -> ResponseReturnValue:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return _bad_request("Expected a JSON object")

        try:
            changes = _alert_changes_from_payload(data, settings=settings, notifiers=notifiers, partial=True)
        except ValueError as exc:
            return _bad_request(str(exc))

        if not changes:
            return _bad_request("No supported fields were provided")

        row = alerts.update_alert(alert_id, changes)
        if row is None:
            return _not_found("Alert not found")
        return jsonify({"data": _alert_to_dict(row)})

    @app.delete("/api/alerts/<int:alert_id>")
    def api_delete_alert(alert_id: int) -> ResponseReturnValue:
        if not alerts.delete_alert(alert_id):
            return _not_found("Alert not found")
        return jsonify({"data": "Alert deleted successfully!"})

    @app.delete("/api/alerts")
    def api_delete_all_alerts() -> ResponseReturnValue:
        deleted = alerts.delete_all_alerts()
        return jsonify({"data": "Alerts deleted successfully!", "deleted": deleted})

    @app.get("/api/events")
    def api_events() -> ResponseReturnValue:
        limit = _clamp_int(request.args.get("limit"), default=50, minimum=1, maximum=500)
        events = alerts.list_events(limit=limit)
        return jsonify({"data": [_event_to_dict(event) for event in events]})

    @app.post("/api/check")
    def api_check_alerts() -> ResponseReturnValue:
        events = engine.evaluate()
        return jsonify(
            {
                "count": len(events),
                "triggered": [_event_to_dict(event, include_deliveries=False) for event in events],
            }
        )

    # ------------------------------------------------------------------
    # Legacy API (kept for scripts built against v0.1)
    # ------------------------------------------------------------------
    @app.get("/metrics")
    def legacy_metrics() -> ResponseReturnValue:
        latest = prices.latest("USDT", "ARS")
        if latest is not None:
            return jsonify({"data": _quote_to_dict(latest)})
        return jsonify({"data": [_quote_to_dict(quote) for quote in prices.latest_all()]})

    @app.post("/api/numbers")
    def legacy_set_thresholds() -> ResponseReturnValue:
        data = request.get_json(silent=True)
        if data is None and request.form:
            data = request.form.to_dict()
        if not isinstance(data, dict):
            return _bad_request("Expected a JSON object")

        currency_type = str(data.get("currency_type", "")).lower()
        if currency_type not in {"buy", "sell"}:
            return _bad_request("Invalid currency_type; expected 'buy' or 'sell'")

        min_num = data.get("min_num")
        max_num = data.get("max_num")
        if min_num in (None, "") and max_num in (None, ""):
            return _bad_request("Please provide min_num or max_num")

        metric = Metric.ASK.value if currency_type == "buy" else Metric.BID.value
        messages: list[str] = []

        for raw_value, operator, label in (
            (min_num, Operator.LESS_THAN.value, f"legacy {currency_type} minimum"),
            (max_num, Operator.GREATER_THAN.value, f"legacy {currency_type} maximum"),
        ):
            if raw_value in (None, ""):
                continue
            try:
                threshold = float(str(raw_value))
            except (TypeError, ValueError):
                return _bad_request(f"Invalid threshold: {raw_value!r}")

            alerts.create_alert(
                asset="USDT",
                quote_currency="ARS",
                metric=metric,
                operator=operator,
                threshold=threshold,
                channels=settings.default_channels,
                cooldown_seconds=settings.default_cooldown_seconds,
                label=label,
            )
            name = "Min" if operator == Operator.LESS_THAN.value else "Max"
            messages.append(f"{name} alert set successfully to {raw_value}")

        return jsonify({"message": " and ".join(messages)})

    @app.delete("/delete/alerts")
    def legacy_delete_all_alerts() -> ResponseReturnValue:
        alerts.delete_all_alerts()
        return jsonify({"data": "Alerts deleted successfully!"})

    @app.delete("/delete/alert/<int:alert_id>")
    def legacy_delete_alert(alert_id: int) -> ResponseReturnValue:
        if not alerts.delete_alert(alert_id):
            return _not_found("Alert not found")
        return jsonify({"data": "Alert deleted successfully!"})

    return app


# ----------------------------------------------------------------------
# Serialisation helpers
# ----------------------------------------------------------------------
def _iso(value: datetime | None) -> str | None:
    return ensure_utc(value).isoformat() if value is not None else None


def _quote_to_dict(quote: Quote) -> dict[str, Any]:
    return {
        "asset": quote.asset,
        "quote_currency": quote.quote_currency,
        "pair": quote.pair,
        "source": quote.source,
        "price": quote.price,
        "bid": quote.bid,
        "ask": quote.ask,
        "volume": quote.volume,
        "timestamp": _iso(quote.timestamp),
        "t": int(quote.timestamp.timestamp() * 1000),
        "tradingview_url": _tradingview_url(quote.asset, quote.quote_currency),
    }


def _stats_to_dict(stats: PriceStats) -> dict[str, Any]:
    return {
        "count": stats.count,
        "min": stats.minimum,
        "max": stats.maximum,
        "avg": stats.average,
        "first": stats.first,
        "last": stats.last,
        "change": stats.change,
        "change_percent": stats.change_percent,
    }


def _alert_to_dict(alert: AlertRow) -> dict[str, Any]:
    return {
        "id": alert.id,
        "asset": alert.asset,
        "quote_currency": alert.quote_currency,
        "pair": f"{alert.asset}/{alert.quote_currency}",
        "metric": alert.metric,
        "operator": alert.operator,
        "threshold": alert.threshold,
        "condition": condition_text(alert),
        "source": alert.source,
        "channels": list(alert.channels or []),
        "cooldown_seconds": alert.cooldown_seconds,
        "repeat": alert.repeat,
        "enabled": alert.enabled,
        "label": alert.label,
        "last_state": alert.last_state,
        "last_triggered_at": _iso(alert.last_triggered_at),
        "created_at": _iso(alert.created_at),
        "updated_at": _iso(alert.updated_at),
    }


def _delivery_to_dict(delivery: DeliveryRow) -> dict[str, Any]:
    return {
        "channel": delivery.channel,
        "success": delivery.success,
        "error": delivery.error,
        "sent_at": _iso(delivery.sent_at),
    }


def _event_to_dict(event: AlertEventRow, *, include_deliveries: bool = True) -> dict[str, Any]:
    return {
        "id": event.id,
        "alert_id": event.alert_id,
        "triggered_at": _iso(event.triggered_at),
        "asset": event.asset,
        "quote_currency": event.quote_currency,
        "pair": f"{event.asset}/{event.quote_currency}",
        "metric": event.metric,
        "operator": event.operator,
        "threshold": event.threshold,
        "value": event.value,
        "source": event.source,
        "message": event.message,
        "deliveries": [_delivery_to_dict(delivery) for delivery in event.deliveries] if include_deliveries else [],
    }


def _pair_overview(
    prices: PriceRepository,
    asset: str,
    quote_currency: str,
    since: datetime | None,
) -> dict[str, Any]:
    quotes = [quote for quote in prices.latest_all() if quote.asset == asset and quote.quote_currency == quote_currency]
    # latest_all is already the latest per source; pick the freshest venue.
    latest = max(quotes, key=lambda quote: (quote.timestamp, quote.source)) if quotes else None
    stats = prices.stats(asset, quote_currency, since)

    return {
        "asset": asset,
        "quote_currency": quote_currency,
        "pair": f"{asset}/{quote_currency}",
        "sources": sorted({quote.source for quote in quotes}),
        "latest": _quote_to_dict(latest) if latest is not None else None,
        "stats": _stats_to_dict(stats),
        "tradingview_url": _tradingview_url(asset, quote_currency),
    }


def _all_pairs(settings: Settings, prices: PriceRepository) -> list[dict[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for pair in configured_pairs(settings):
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    for row in prices.pairs():
        pair = (str(row["asset"]), str(row["quote_currency"]))
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)

    return [
        {
            "asset": asset,
            "quote_currency": quote_currency,
            "pair": f"{asset}/{quote_currency}",
            "tradingview_url": _tradingview_url(asset, quote_currency),
        }
        for asset, quote_currency in sorted(pairs)
    ]


def _data_pairs(prices: PriceRepository) -> list[tuple[str, str]]:
    return [(str(row["asset"]), str(row["quote_currency"])) for row in prices.pairs()]


def _downsample(quotes: Iterable[Quote], max_points: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[Quote]] = defaultdict(list)
    for quote in quotes:
        grouped[quote.source].append(quote)

    per_source = max(2, max_points // max(1, len(grouped)))
    points: list[dict[str, Any]] = []
    for source_quotes in grouped.values():
        if len(source_quotes) > per_source:
            step = math.ceil(len(source_quotes) / per_source)
            selected = source_quotes[::step]
            if selected[-1] is not source_quotes[-1]:
                selected.append(source_quotes[-1])
        else:
            selected = source_quotes

        points.extend(
            {
                "t": int(quote.timestamp.timestamp() * 1000),
                "timestamp": _iso(quote.timestamp),
                "price": quote.price,
                "bid": quote.bid,
                "ask": quote.ask,
                "source": quote.source,
            }
            for quote in selected
        )

    points.sort(key=lambda point: point["t"])
    return points


def _alert_changes_from_payload(
    data: dict[str, Any],
    *,
    settings: Settings,
    notifiers: NotifierRegistry,
    partial: bool,
) -> dict[str, Any]:
    changes: dict[str, Any] = {}

    if not partial or "asset" in data:
        asset = str(data.get("asset") or "").strip().upper()
        if not asset:
            raise ValueError("asset is required")
        changes["asset"] = asset

    if not partial or "quote_currency" in data or "quote" in data:
        quote_currency = str(data.get("quote_currency") or data.get("quote") or "").strip().upper()
        if not quote_currency:
            raise ValueError("quote_currency is required")
        changes["quote_currency"] = quote_currency

    if not partial or "metric" in data:
        metric_raw = str(data.get("metric", "price")).lower()
        try:
            changes["metric"] = Metric(metric_raw).value
        except ValueError as exc:
            allowed = ", ".join(metric.value for metric in Metric)
            raise ValueError(f"Invalid metric {metric_raw!r}; expected one of: {allowed}") from exc

    if not partial or "operator" in data:
        operator_raw = str(data.get("operator", ">"))
        try:
            changes["operator"] = Operator(operator_raw).value
        except ValueError as exc:
            allowed = ", ".join(operator.value for operator in Operator)
            raise ValueError(f"Invalid operator {operator_raw!r}; expected one of: {allowed}") from exc

    if not partial or "threshold" in data:
        if "threshold" not in data:
            raise ValueError("threshold is required")
        try:
            threshold = float(data["threshold"])
        except (TypeError, ValueError) as exc:
            raise ValueError("threshold must be a number") from exc
        if not math.isfinite(threshold):
            raise ValueError("threshold must be finite")
        changes["threshold"] = threshold

    if "source" in data:
        changes["source"] = str(data.get("source") or "").strip() or None

    if not partial or "channels" in data:
        raw_channels = data.get("channels", settings.default_channels)
        changes["channels"] = _validated_channels(raw_channels, notifiers=notifiers)

    if "cooldown_seconds" in data or not partial:
        try:
            cooldown = int(data.get("cooldown_seconds", settings.default_cooldown_seconds))
        except (TypeError, ValueError) as exc:
            raise ValueError("cooldown_seconds must be an integer") from exc
        changes["cooldown_seconds"] = max(0, cooldown)

    if "repeat" in data or not partial:
        changes["repeat"] = _as_bool(data.get("repeat", False))

    if "enabled" in data or not partial:
        changes["enabled"] = _as_bool(data.get("enabled", True))

    if "label" in data:
        changes["label"] = str(data.get("label") or "").strip() or None

    return changes


def _validated_channels(raw: Any, *, notifiers: NotifierRegistry) -> list[str]:
    if raw is None:
        channels: list[str] = []
    elif isinstance(raw, str):
        channels = [part.strip().lower() for part in raw.replace(";", ",").split(",")]
    elif isinstance(raw, (list, tuple, set)):
        channels = [str(channel).strip().lower() for channel in raw]
    else:
        raise ValueError("channels must be a list of channel names")

    channels = [channel for channel in dict.fromkeys(channels) if channel]
    unknown = [channel for channel in channels if not notifiers.has(channel)]
    if unknown:
        available = ", ".join(notifiers.channels()) or "none"
        raise ValueError(f"Unknown notifier channel(s): {', '.join(unknown)}. Available: {available}")
    return channels


def _range_from_request() -> tuple[str, datetime | None, tuple[Response, int] | None]:
    range_key = (request.args.get("range") or "24h").lower()
    try:
        return range_key, range_since(range_key), None
    except ValueError:
        allowed = ", ".join(RANGE_DELTAS)
        return range_key, None, _bad_request(f"Invalid range {range_key!r}; expected one of: {allowed}")


def _tradingview_url(asset: str, quote_currency: str) -> str:
    return f"https://www.tradingview.com/symbols/{asset.upper()}{quote_currency.upper()}/"


def _enabled_provider_names(settings: Settings) -> list[str]:
    names: list[str] = []
    if settings.binance.enabled and settings.binance.symbols:
        names.append("binance")
    if settings.criptoya.enabled and settings.criptoya.exchanges:
        names.append("criptoya")
    if settings.coingecko.enabled and settings.coingecko.assets:
        names.append("coingecko")
    return names


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _clamp_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _bad_request(message: str) -> tuple[Response, int]:
    return jsonify({"error": message}), 400


def _not_found(message: str) -> tuple[Response, int]:
    return jsonify({"error": message}), 404
