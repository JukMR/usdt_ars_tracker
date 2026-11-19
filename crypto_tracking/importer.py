"""CSV import helpers.

Supports both the legacy ``timestamp,source,buy,sell`` layout and a modern
``timestamp,asset,quote_currency,source,price,bid,ask,volume`` layout.
"""

from __future__ import annotations

import csv
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_tracking.domain import Quote
from crypto_tracking.storage.repositories import PriceRepository

logger = logging.getLogger(__name__)


def import_csv(
    path: Path | str,
    prices: PriceRepository,
    *,
    default_asset: str = "USDT",
    default_quote_currency: str = "ARS",
    default_source: str = "csv",
    chunk_size: int = 1000,
) -> int:
    """Import a price CSV and return the number of new rows stored."""
    csv_path = Path(path).expanduser()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    inserted = 0
    batch: list[Quote] = []
    skipped = 0

    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV file has no header row")

        for line_number, raw_row in enumerate(reader, start=2):
            row = _normalise_row(raw_row)
            try:
                quote = _row_to_quote(
                    row,
                    default_asset=default_asset,
                    default_quote_currency=default_quote_currency,
                    default_source=default_source,
                )
            except (KeyError, TypeError, ValueError) as exc:
                skipped += 1
                logger.warning("Skipping CSV row %d: %s", line_number, exc)
                continue

            batch.append(quote)
            if len(batch) >= chunk_size:
                inserted += prices.add_quotes(batch)
                batch.clear()

    if batch:
        inserted += prices.add_quotes(batch)

    if skipped:
        logger.warning("Skipped %d invalid CSV row(s)", skipped)
    return inserted


def _normalise_row(raw_row: dict[str, Any]) -> dict[str, str]:
    return {str(key).strip().lower(): str(value).strip() for key, value in raw_row.items() if key is not None}


def _row_to_quote(
    row: dict[str, str],
    *,
    default_asset: str,
    default_quote_currency: str,
    default_source: str,
) -> Quote:
    timestamp_raw = _first_present(row, "timestamp", "datetime", "time")
    if timestamp_raw is None:
        raise ValueError("missing timestamp column")

    timestamp = parse_timestamp(timestamp_raw)
    asset = (row.get("asset") or default_asset).upper()
    quote_currency = (row.get("quote_currency") or row.get("quote") or default_quote_currency).upper()
    source = row.get("source") or default_source

    price_raw = row.get("price")
    buy_raw = row.get("buy")
    sell_raw = row.get("sell")
    bid_raw = row.get("bid")
    ask_raw = row.get("ask")

    bid = _to_float(bid_raw)
    ask = _to_float(ask_raw)

    # Legacy semantics: "buy" was the price you buy at (ask) and "sell" was
    # the price you sell at (bid).
    if bid is None and sell_raw:
        bid = _to_float(sell_raw)
    if ask is None and buy_raw:
        ask = _to_float(buy_raw)

    if price_raw:
        price = _to_float(price_raw)
    elif bid is not None and ask is not None:
        price = (bid + ask) / 2
    elif ask is not None:
        price = ask
    elif bid is not None:
        price = bid
    else:
        raise ValueError("missing price/buy/sell columns")

    if price is None or price <= 0:
        raise ValueError("price must be positive")

    return Quote(
        asset=asset,
        quote_currency=quote_currency,
        source=source,
        price=price,
        bid=bid,
        ask=ask,
        volume=_to_float(row.get("volume")),
        timestamp=timestamp,
    )


def _first_present(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if row.get(key):
            return row[key]
    return None


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def parse_timestamp(raw: str) -> datetime:
    """Parse common CSV timestamp formats, treating naive values as UTC."""
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = _parse_with_formats(value)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_with_formats(value: str) -> datetime:
    formats = (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)  # noqa: DTZ007 - naive values are treated as UTC by the caller
        except ValueError:
            continue
    raise ValueError(f"Unrecognised timestamp: {value!r}")
