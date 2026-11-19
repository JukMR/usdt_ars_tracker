from __future__ import annotations

import json

import pytest

from crypto_tracking.providers.binance import BinanceProvider, split_symbol
from crypto_tracking.providers.coingecko import CoinGeckoProvider
from crypto_tracking.providers.criptoya import CriptoyaProvider


class FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(self.payload)


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("BTCUSDT", ("BTC", "USDT")),
        ("ETHUSDT", ("ETH", "USDT")),
        ("ETHBTC", ("ETH", "BTC")),
        ("SOLUSDC", ("SOL", "USDC")),
        ("NOTAPAIR", None),
    ],
)
def test_split_symbol(symbol, expected):
    assert split_symbol(symbol) == expected


def test_binance_fetch_parses_payload():
    session = FakeSession(
        [
            {
                "symbol": "BTCUSDT",
                "lastPrice": "62000.5",
                "bidPrice": "61999.0",
                "askPrice": "62001.0",
                "quoteVolume": "1234.5",
                "closeTime": 1700000000000,
            },
            {
                "symbol": "ETHUSDT",
                "lastPrice": "3000",
                "bidPrice": "0",
                "askPrice": "3001",
                "quoteVolume": "999",
                "closeTime": 1700000000000,
            },
        ]
    )
    provider = BinanceProvider(["BTCUSDT", "ETHUSDT"], session=session)

    quotes = provider.fetch()
    assert len(quotes) == 2

    bitcoin = next(quote for quote in quotes if quote.asset == "BTC")
    assert bitcoin.quote_currency == "USDT"
    assert bitcoin.price == 62000.5
    assert bitcoin.bid == 61999.0
    assert bitcoin.ask == 62001.0
    assert bitcoin.volume == 1234.5
    assert bitcoin.source == "binance"

    ethereum = next(quote for quote in quotes if quote.asset == "ETH")
    assert ethereum.bid is None

    params = session.calls[0]["params"]
    assert json.loads(params["symbols"]) == ["BTCUSDT", "ETHUSDT"]


def test_binance_error_payload_raises():
    provider = BinanceProvider(["BTCUSDT"], session=FakeSession({"code": -1121, "msg": "Invalid symbol"}))
    with pytest.raises(ValueError, match="Binance error"):
        provider.fetch()


def test_binance_single_symbol_dict_payload():
    provider = BinanceProvider(
        ["BTCUSDT"],
        session=FakeSession(
            {
                "symbol": "BTCUSDT",
                "lastPrice": "1",
                "bidPrice": "1",
                "askPrice": "1",
                "closeTime": 0,
            }
        ),
    )
    quotes = provider.fetch()
    assert len(quotes) == 1
    assert quotes[0].timestamp.tzinfo is not None


def test_binance_pairs_and_unknown_symbols():
    provider = BinanceProvider(["BTCUSDT", "NOPE"], session=FakeSession([]))
    assert provider.pairs() == [("BTC", "USDT")]


def test_criptoya_fetch_uses_configured_exchange():
    session = FakeSession(
        {
            "buenbit": {"ask": 1700, "totalAsk": 1710, "bid": 1690, "totalBid": 1680, "time": 1700000000},
            "ripio": {"ask": 1800, "totalAsk": 1801, "bid": 1790, "totalBid": 1789, "time": 1700000000},
        }
    )
    provider = CriptoyaProvider(coin="usdt", fiat="ars", exchanges=["buenbit"], session=session)

    quotes = provider.fetch()
    assert len(quotes) == 1
    quote = quotes[0]
    assert quote.asset == "USDT"
    assert quote.quote_currency == "ARS"
    assert quote.source == "criptoya:buenbit"
    assert quote.ask == 1710
    assert quote.bid == 1680
    assert quote.price == 1695
    assert session.calls[0]["url"].endswith("/usdt/ars")


def test_criptoya_falls_back_to_ask_bid_and_skips_missing_exchange():
    session = FakeSession({"buenbit": {"ask": 100, "bid": 90, "time": 0}})
    provider = CriptoyaProvider(exchanges=["buenbit", "missing"], session=session)

    quotes = provider.fetch()
    assert len(quotes) == 1
    assert quotes[0].ask == 100
    assert quotes[0].bid == 90
    assert quotes[0].price == 95


def test_criptoya_pairs():
    provider = CriptoyaProvider(coin="usdt", fiat="ars", exchanges=["buenbit"], session=FakeSession({}))
    assert provider.pairs() == [("USDT", "ARS")]


def test_criptoya_empty_exchanges_fetches_every_venue():
    session = FakeSession(
        {
            "ripio": {"ask": 100, "bid": 90, "time": 0},
            "letsbit": {"ask": 110, "bid": 100, "time": 0},
        }
    )
    provider = CriptoyaProvider(exchanges=[], session=session)

    quotes = provider.fetch()
    assert [quote.source for quote in quotes] == ["criptoya:ripio", "criptoya:letsbit"]
    assert provider.pairs() == [("USDT", "ARS")]


def test_coingecko_fetch():
    session = FakeSession({"bitcoin": {"usd": 62000}, "ethereum": {"usd": 3000}})
    provider = CoinGeckoProvider(assets={"bitcoin": "BTC", "ethereum": "ETH"}, session=session)

    quotes = provider.fetch()
    assert len(quotes) == 2
    assert {quote.asset for quote in quotes} == {"BTC", "ETH"}
    assert all(quote.quote_currency == "USD" for quote in quotes)
    assert session.calls[0]["params"]["vs_currencies"] == "usd"


def test_coingecko_missing_asset_is_skipped():
    provider = CoinGeckoProvider(
        assets={"bitcoin": "BTC", "ethereum": "ETH"},
        session=FakeSession({"bitcoin": {"usd": 62000}}),
    )
    quotes = provider.fetch()
    assert [quote.asset for quote in quotes] == ["BTC"]
    assert provider.pairs() == [("BTC", "USD"), ("ETH", "USD")]
