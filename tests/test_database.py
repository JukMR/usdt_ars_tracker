from __future__ import annotations

from sqlalchemy import inspect, text

from crypto_tracking.storage.database import Database


def test_sqlite_keeps_only_the_composite_indexes(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'indexes.db'}")
    database.create_all()

    # Simulate a database created by an older version with per-column indexes.
    with database.engine.begin() as connection:
        connection.execute(text("CREATE INDEX ix_prices_asset ON prices (asset)"))
        connection.execute(text("CREATE INDEX ix_prices_source ON prices (source)"))
        connection.execute(text("DROP INDEX ix_prices_pair_source_time"))

    database.create_all()

    names = {index["name"] for index in inspect(database.engine).get_indexes("prices")}
    assert "ix_prices_asset" not in names
    assert "ix_prices_source" not in names
    assert "ix_prices_pair_time" in names
    assert "ix_prices_pair_source_time" in names

    database.dispose()
