from __future__ import annotations

import pytest

from crypto_tracking.domain import utcnow
from crypto_tracking.importer import import_csv, parse_timestamp
from crypto_tracking.storage.repositories import PriceRepository


def test_import_legacy_csv(db, tmp_path):
    csv_path = tmp_path / "legacy.csv"
    csv_path.write_text(
        "Timestamp,Source,Buy,Sell\n"
        "2024-07-28 12:47:18.504574,buenbit,1342.92,1327.0\n"
        "2024-07-28 12:48:18.934154,buenbit,1342.95,1327.03\n",
        encoding="utf-8",
    )

    prices = PriceRepository(db)
    inserted = import_csv(csv_path, prices)

    assert inserted == 2
    latest = prices.latest("USDT", "ARS")
    assert latest is not None
    assert latest.source == "buenbit"
    assert latest.ask == 1342.95
    assert latest.bid == 1327.03
    assert latest.price == pytest.approx((1342.95 + 1327.03) / 2)


def test_import_modern_csv(db, tmp_path):
    csv_path = tmp_path / "modern.csv"
    csv_path.write_text(
        "timestamp,asset,quote_currency,source,price,bid,ask,volume\n"
        "2024-01-01T00:00:00Z,BTC,USDT,binance,62000,61999,62001,10\n",
        encoding="utf-8",
    )

    prices = PriceRepository(db)
    assert import_csv(csv_path, prices) == 1

    quote = prices.latest("BTC", "USDT")
    assert quote is not None
    assert quote.price == 62000
    assert quote.volume == 10


def test_import_skips_invalid_rows(db, tmp_path):
    csv_path = tmp_path / "mixed.csv"
    csv_path.write_text(
        "timestamp,source,buy,sell\n"
        "not-a-date,buenbit,1,2\n"
        "2024-01-01 00:00:00,buenbit,,,\n"
        "2024-01-01 00:01:00,buenbit,10,9\n",
        encoding="utf-8",
    )

    prices = PriceRepository(db)
    assert import_csv(csv_path, prices) == 1
    assert prices.count() == 1


def test_import_uses_defaults(db, tmp_path):
    csv_path = tmp_path / "no_source.csv"
    csv_path.write_text("timestamp,price\n2024-01-01 00:00:00,100\n", encoding="utf-8")

    prices = PriceRepository(db)
    assert import_csv(csv_path, prices, default_asset="ETH", default_quote_currency="USD", default_source="file") == 1

    quote = prices.latest("ETH", "USD")
    assert quote is not None
    assert quote.source == "file"


def test_import_missing_file(db, tmp_path):
    with pytest.raises(FileNotFoundError):
        import_csv(tmp_path / "missing.csv", PriceRepository(db))


@pytest.mark.parametrize(
    "raw",
    [
        "2024-01-01 12:00:00",
        "2024-01-01 12:00:00.123456",
        "2024-01-01T12:00:00",
        "2024-01-01T12:00:00Z",
        "2024/01/01 12:00:00",
    ],
)
def test_parse_timestamp_formats(raw):
    parsed = parse_timestamp(raw)
    assert parsed.year == 2024
    assert parsed.tzinfo is not None


def test_parse_timestamp_rejects_garbage():
    with pytest.raises(ValueError):
        parse_timestamp("yesterday")


def test_import_does_not_duplicate_rows(db, tmp_path):
    csv_path = tmp_path / "dupes.csv"
    csv_path.write_text(
        f"timestamp,asset,quote_currency,source,price\n{utcnow().isoformat()},BTC,USDT,binance,100\n",
        encoding="utf-8",
    )

    prices = PriceRepository(db)
    assert import_csv(csv_path, prices) == 1
    assert import_csv(csv_path, prices) == 0
    assert prices.count() == 1
