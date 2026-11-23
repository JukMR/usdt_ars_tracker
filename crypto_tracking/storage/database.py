"""Database lifecycle helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from crypto_tracking.storage.models import Base

logger = logging.getLogger(__name__)

# One index per column was redundant with the composite indexes below and only
# made inserts and files bigger. They are dropped from existing databases.
LEGACY_SQLITE_INDEXES = (
    "ix_prices_timestamp",
    "ix_prices_asset",
    "ix_prices_quote_currency",
    "ix_prices_source",
)


class Database:
    """Owns the SQLAlchemy engine and session factory."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        self._prepare_sqlite_directory(url)

        engine_kwargs: dict[str, object] = {"future": True, "echo": echo}
        if url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url:
                engine_kwargs["poolclass"] = StaticPool

        self.engine: Engine = create_engine(url, **engine_kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _configure_sqlite_connection)

        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        """Create missing tables and apply the SQLite storage optimisations."""
        Base.metadata.create_all(self.engine)
        if self.url.startswith("sqlite"):
            self._optimise_sqlite(self.engine)

    @staticmethod
    def _optimise_sqlite(engine: Engine) -> None:
        """Keep the price table compact and refresh the query planner statistics.

        Earlier versions created one index per column plus a composite index;
        the single-column indexes duplicate work already covered by the composite
        ones and add a large write/storage cost for a table that grows forever.
        Drop them if an existing database still has them, then let SQLite update
        its statistics.
        """
        with engine.begin() as connection:
            for index_name in LEGACY_SQLITE_INDEXES:
                connection.execute(text(f'DROP INDEX IF EXISTS "{index_name}"'))
            connection.execute(text("PRAGMA optimize"))

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Provide a transactional session scope."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()

    @staticmethod
    def _prepare_sqlite_directory(url: str) -> None:
        prefix = "sqlite:///"
        if not url.startswith(prefix):
            return

        path_part = url[len(prefix) :]
        if not path_part or path_part == ":memory:" or path_part.startswith("file:"):
            return

        Path(path_part).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite_connection(dbapi_connection: object, _connection_record: object) -> None:
    """Enable foreign keys and a busy timeout for SQLite connections."""
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except Exception:  # pragma: no cover - in-memory databases cannot use WAL
            logger.debug("Could not enable WAL mode", exc_info=True)
    finally:
        cursor.close()
