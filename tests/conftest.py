from __future__ import annotations

import pytest

from crypto_tracking.alerts.engine import AlertEngine
from crypto_tracking.config import BinanceConfig, CoinGeckoConfig, CriptoyaConfig, Settings
from crypto_tracking.notifiers.log import LogNotifier
from crypto_tracking.notifiers.registry import NotifierRegistry
from crypto_tracking.storage.database import Database
from crypto_tracking.storage.repositories import AlertRepository, PriceRepository
from crypto_tracking.web.app import create_app


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'test.db'}")
    database.create_all()
    yield database
    database.dispose()


@pytest.fixture
def repos(db):
    return PriceRepository(db), AlertRepository(db)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        project_root=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        binance=BinanceConfig(enabled=False, symbols=[]),
        criptoya=CriptoyaConfig(enabled=False),
        coingecko=CoinGeckoConfig(enabled=False),
        default_channels=["log"],
    )


@pytest.fixture
def registry():
    result = NotifierRegistry()
    result.register(LogNotifier())
    return result


@pytest.fixture
def engine(repos, registry):
    prices, alerts = repos
    return AlertEngine(alerts, prices, registry)


@pytest.fixture
def app(settings, repos, registry, engine):
    prices, alerts = repos
    application = create_app(
        settings=settings,
        prices=prices,
        alerts=alerts,
        engine=engine,
        notifiers=registry,
    )
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(app):
    return app.test_client()
