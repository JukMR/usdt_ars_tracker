"""SQLAlchemy ORM models for prices, alerts and alert history."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from crypto_tracking.domain import utcnow


class Base(DeclarativeBase):
    """Base class for all database models."""


class PriceRow(Base):
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "timestamp",
            "asset",
            "quote_currency",
            "source",
            name="uq_prices_point",
        ),
        Index("ix_prices_pair_time", "asset", "quote_currency", "timestamp"),
        Index("ix_prices_pair_source_time", "asset", "quote_currency", "source", "timestamp"),
    )


class AlertRow(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    metric: Mapped[str] = mapped_column(String(16), nullable=False, default="price")
    operator: Mapped[str] = mapped_column(String(4), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    repeat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Edge-trigger state: None means "not evaluated yet", False means the
    # condition is currently false, True means it is currently true.
    last_state: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    events: Mapped[list[AlertEventRow]] = relationship(back_populates="alert", passive_deletes=True)

    __table_args__ = (Index("ix_alerts_pair", "asset", "quote_currency"),)


class AlertEventRow(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Snapshot of the alert and market data at trigger time. Keeping this
    # denormalised means history remains readable after an alert is deleted.
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    metric: Mapped[str] = mapped_column(String(16), nullable=False)
    operator: Mapped[str] = mapped_column(String(4), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    alert: Mapped[AlertRow | None] = relationship(back_populates="events")
    deliveries: Mapped[list[DeliveryRow]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DeliveryRow(Base):
    __tablename__ = "alert_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("alert_events.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    event: Mapped[AlertEventRow] = relationship(back_populates="deliveries")
