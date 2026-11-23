"""Repository layer: all database access lives here."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from crypto_tracking.domain import PriceStats, Quote, ensure_utc, utcnow
from crypto_tracking.storage.database import Database
from crypto_tracking.storage.models import AlertEventRow, AlertRow, DeliveryRow, PriceRow

logger = logging.getLogger(__name__)


class PriceRepository:
    """Read/write access to price observations."""

    def __init__(self, database: Database) -> None:
        self.db = database

    def add_quotes(self, quotes: Iterable[Quote]) -> int:
        """Insert quotes, ignoring duplicates. Returns the number inserted."""
        quote_list = list(quotes)
        if not quote_list:
            return 0

        inserted = 0
        with self.db.session() as session:
            dialect_name = session.bind.dialect.name if session.bind is not None else "sqlite"
            for quote in quote_list:
                values = {
                    "timestamp": ensure_utc(quote.timestamp),
                    "asset": quote.asset,
                    "quote_currency": quote.quote_currency,
                    "source": quote.source,
                    "price": float(quote.price),
                    "bid": quote.bid,
                    "ask": quote.ask,
                    "volume": quote.volume,
                }

                if dialect_name == "sqlite":
                    statement = (
                        sqlite_insert(PriceRow)
                        .values(**values)
                        .on_conflict_do_nothing(index_elements=["timestamp", "asset", "quote_currency", "source"])
                    )
                    result = session.execute(statement)
                    inserted += max(int(getattr(result, "rowcount", 0) or 0), 0)
                else:  # pragma: no cover - SQLite is the supported backend
                    try:
                        with session.begin_nested():
                            session.add(PriceRow(**values))
                        inserted += 1
                    except IntegrityError:
                        logger.debug("Ignoring duplicate price point for %s", quote.pair)

        return inserted

    def latest(self, asset: str, quote_currency: str, source: str | None = None) -> Quote | None:
        """Return the most recent quote for a pair, optionally filtered by source."""
        statement = select(PriceRow).where(
            PriceRow.asset == asset.upper(),
            PriceRow.quote_currency == quote_currency.upper(),
        )
        if source:
            statement = statement.where(PriceRow.source == source)
        statement = statement.order_by(PriceRow.timestamp.desc(), PriceRow.id.desc()).limit(1)

        with self.db.session() as session:
            row = session.scalar(statement)
        return _row_to_quote(row) if row is not None else None

    def latest_all(self) -> list[Quote]:
        """Return the latest quote for every (asset, quote, source) tuple."""
        latest = (
            select(
                PriceRow.asset.label("asset"),
                PriceRow.quote_currency.label("quote_currency"),
                PriceRow.source.label("source"),
                func.max(PriceRow.timestamp).label("max_timestamp"),
            )
            .group_by(PriceRow.asset, PriceRow.quote_currency, PriceRow.source)
            .subquery()
        )

        statement = (
            select(PriceRow)
            .join(
                latest,
                and_(
                    PriceRow.asset == latest.c.asset,
                    PriceRow.quote_currency == latest.c.quote_currency,
                    PriceRow.source == latest.c.source,
                    PriceRow.timestamp == latest.c.max_timestamp,
                ),
            )
            .order_by(PriceRow.asset, PriceRow.quote_currency, PriceRow.source)
        )

        with self.db.session() as session:
            rows = list(session.scalars(statement))
        return [_row_to_quote(row) for row in rows]

    def history(
        self,
        asset: str,
        quote_currency: str,
        *,
        since: datetime | None = None,
        source: str | None = None,
        limit: int | None = 5000,
    ) -> list[Quote]:
        """Return history in chronological order.

        When ``limit`` is set, the most recent ``limit`` points are returned.
        """
        conditions = [
            PriceRow.asset == asset.upper(),
            PriceRow.quote_currency == quote_currency.upper(),
        ]
        if since is not None:
            conditions.append(PriceRow.timestamp >= ensure_utc(since))
        if source:
            conditions.append(PriceRow.source == source)

        statement = select(PriceRow).where(*conditions)
        with self.db.session() as session:
            if limit is None:
                rows = list(session.scalars(statement.order_by(PriceRow.timestamp.asc(), PriceRow.id.asc())))
            else:
                rows = list(
                    session.scalars(statement.order_by(PriceRow.timestamp.desc(), PriceRow.id.desc()).limit(limit))
                )
                rows.reverse()

        return [_row_to_quote(row) for row in rows]

    def stats(self, asset: str, quote_currency: str, since: datetime | None = None) -> PriceStats:
        """Aggregate price statistics for a pair over an optional window."""
        conditions = [
            PriceRow.asset == asset.upper(),
            PriceRow.quote_currency == quote_currency.upper(),
        ]
        if since is not None:
            conditions.append(PriceRow.timestamp >= ensure_utc(since))

        aggregate_statement = select(
            func.min(PriceRow.price),
            func.max(PriceRow.price),
            func.avg(PriceRow.price),
            func.count(PriceRow.id),
        ).where(*conditions)

        with self.db.session() as session:
            minimum, maximum, average, count = session.execute(aggregate_statement).one()
            count = int(count or 0)
            if count == 0:
                return PriceStats(count=0, minimum=None, maximum=None, average=None, first=None, last=None)

            first = session.scalar(
                select(PriceRow.price).where(*conditions).order_by(PriceRow.timestamp.asc(), PriceRow.id.asc()).limit(1)
            )
            last = session.scalar(
                select(PriceRow.price)
                .where(*conditions)
                .order_by(PriceRow.timestamp.desc(), PriceRow.id.desc())
                .limit(1)
            )

        return PriceStats(
            count=count,
            minimum=minimum,
            maximum=maximum,
            average=average,
            first=first,
            last=last,
        )

    def pairs(self) -> list[dict[str, object]]:
        """Return every pair that has stored prices."""
        statement = (
            select(
                PriceRow.asset,
                PriceRow.quote_currency,
                func.count(PriceRow.id).label("price_count"),
                func.min(PriceRow.timestamp).label("first_timestamp"),
                func.max(PriceRow.timestamp).label("last_timestamp"),
            )
            .group_by(PriceRow.asset, PriceRow.quote_currency)
            .order_by(PriceRow.asset, PriceRow.quote_currency)
        )

        with self.db.session() as session:
            rows = session.execute(statement).all()

        return [
            {
                "asset": row.asset,
                "quote_currency": row.quote_currency,
                "count": int(row.price_count),
                "first_timestamp": ensure_utc(row.first_timestamp) if row.first_timestamp else None,
                "last_timestamp": ensure_utc(row.last_timestamp) if row.last_timestamp else None,
            }
            for row in rows
        ]

    def count(self) -> int:
        with self.db.session() as session:
            return int(session.scalar(select(func.count(PriceRow.id))) or 0)

    def latest_timestamp(self) -> datetime | None:
        """Timestamp of the newest stored price (``None`` when the table is empty)."""
        with self.db.session() as session:
            value = session.scalar(select(func.max(PriceRow.timestamp)))
        return ensure_utc(value) if value is not None else None

    def oldest_timestamp(self) -> datetime | None:
        """Timestamp of the oldest stored price (``None`` when the table is empty)."""
        with self.db.session() as session:
            value = session.scalar(select(func.min(PriceRow.timestamp)))
        return ensure_utc(value) if value is not None else None


class AlertRepository:
    """CRUD for alerts plus append-only alert event history."""

    def __init__(self, database: Database) -> None:
        self.db = database

    def create_alert(
        self,
        *,
        asset: str,
        quote_currency: str,
        metric: str,
        operator: str,
        threshold: float,
        source: str | None = None,
        channels: Sequence[str] | None = None,
        cooldown_seconds: int = 3600,
        repeat: bool = False,
        enabled: bool = True,
        label: str | None = None,
    ) -> AlertRow:
        now = utcnow()
        row = AlertRow(
            asset=asset.upper(),
            quote_currency=quote_currency.upper(),
            metric=metric,
            operator=operator,
            threshold=float(threshold),
            source=source or None,
            channels=list(dict.fromkeys(channels or [])),
            cooldown_seconds=max(0, int(cooldown_seconds)),
            repeat=bool(repeat),
            enabled=bool(enabled),
            label=(label or None),
            created_at=now,
            updated_at=now,
        )

        with self.db.session() as session:
            session.add(row)
            session.flush()
            session.refresh(row)

        return row

    def list_alerts(self, *, enabled_only: bool = False) -> list[AlertRow]:
        statement = select(AlertRow).order_by(AlertRow.id.asc())
        if enabled_only:
            statement = statement.where(AlertRow.enabled.is_(True))

        with self.db.session() as session:
            return list(session.scalars(statement))

    def get_alert(self, alert_id: int) -> AlertRow | None:
        with self.db.session() as session:
            return session.get(AlertRow, alert_id)

    def update_alert(self, alert_id: int, changes: dict[str, Any]) -> AlertRow | None:
        allowed = {
            "asset",
            "quote_currency",
            "metric",
            "operator",
            "threshold",
            "source",
            "channels",
            "cooldown_seconds",
            "repeat",
            "enabled",
            "label",
        }
        state_resetting_fields = {"asset", "quote_currency", "metric", "operator", "threshold", "source"}

        with self.db.session() as session:
            row = session.get(AlertRow, alert_id)
            if row is None:
                return None

            changed = False
            for key, value in changes.items():
                if key not in allowed:
                    continue
                if key in {"asset", "quote_currency"} and value is not None:
                    value = str(value).upper()
                if key == "channels" and value is not None:
                    value = list(dict.fromkeys(str(channel) for channel in value))
                if key in {"source", "label"} and value == "":
                    value = None
                if key == "threshold" and value is not None:
                    value = float(value)
                if key == "cooldown_seconds" and value is not None:
                    value = max(0, int(value))

                setattr(row, key, value)
                changed = True

            if changed:
                if changes.get("enabled") is True:
                    row.last_state = None
                if state_resetting_fields & set(changes):
                    row.last_state = None
                row.updated_at = utcnow()

            session.flush()
            session.refresh(row)

        return row

    def delete_alert(self, alert_id: int) -> bool:
        with self.db.session() as session:
            row = session.get(AlertRow, alert_id)
            if row is None:
                return False
            session.delete(row)
        return True

    def delete_all_alerts(self) -> int:
        with self.db.session() as session:
            result = session.execute(delete(AlertRow))
            return int(getattr(result, "rowcount", 0) or 0)

    def count_alerts(self) -> int:
        with self.db.session() as session:
            return int(session.scalar(select(func.count(AlertRow.id))) or 0)

    def set_last_state(self, alert_id: int, state: bool) -> None:
        with self.db.session() as session:
            row = session.get(AlertRow, alert_id)
            if row is not None:
                row.last_state = state
                row.updated_at = utcnow()

    def mark_triggered(self, alert_id: int, triggered_at: datetime | None = None) -> None:
        with self.db.session() as session:
            row = session.get(AlertRow, alert_id)
            if row is not None:
                row.last_triggered_at = ensure_utc(triggered_at or utcnow())
                row.updated_at = utcnow()

    def record_event(
        self,
        alert: AlertRow,
        *,
        value: float,
        source: str,
        message: str,
        triggered_at: datetime | None = None,
    ) -> AlertEventRow:
        row = AlertEventRow(
            alert_id=alert.id,
            triggered_at=ensure_utc(triggered_at or utcnow()),
            asset=alert.asset,
            quote_currency=alert.quote_currency,
            metric=alert.metric,
            operator=alert.operator,
            threshold=alert.threshold,
            value=float(value),
            source=source,
            message=message,
        )
        with self.db.session() as session:
            session.add(row)
            session.flush()
            session.refresh(row)
        return row

    def record_delivery(self, event_id: int, channel: str, *, success: bool, error: str | None = None) -> DeliveryRow:
        row = DeliveryRow(
            event_id=event_id,
            channel=channel,
            success=success,
            error=error,
            sent_at=utcnow(),
        )
        with self.db.session() as session:
            session.add(row)
            session.flush()
            session.refresh(row)
        return row

    def list_events(self, limit: int = 100) -> list[AlertEventRow]:
        statement = (
            select(AlertEventRow)
            .options(selectinload(AlertEventRow.deliveries))
            .order_by(AlertEventRow.triggered_at.desc(), AlertEventRow.id.desc())
            .limit(max(1, min(limit, 500)))
        )
        with self.db.session() as session:
            return list(session.scalars(statement))

    def count_events(self) -> int:
        with self.db.session() as session:
            return int(session.scalar(select(func.count(AlertEventRow.id))) or 0)


def _row_to_quote(row: PriceRow) -> Quote:
    return Quote(
        asset=row.asset,
        quote_currency=row.quote_currency,
        source=row.source,
        price=row.price,
        bid=row.bid,
        ask=row.ask,
        volume=row.volume,
        timestamp=ensure_utc(row.timestamp),
    )
