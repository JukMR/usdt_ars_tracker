from __future__ import annotations

import pytest

from crypto_tracking.config import load_settings

CONFIG_KEYS = [
    "CT_CONFIG",
    "CT_DATABASE_URL",
    "CT_HOST",
    "CT_PORT",
    "CT_DEBUG",
    "CT_LOG_LEVEL",
    "CT_POLL_INTERVAL",
    "CT_BINANCE_SYMBOLS",
    "CT_BINANCE_ENABLED",
    "CT_CRIPTOYA_ENABLED",
    "CT_CRIPTOYA_COIN",
    "CT_CRIPTOYA_FIAT",
    "CT_CRIPTOYA_EXCHANGES",
    "CT_COINGECKO_ENABLED",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults(tmp_path):
    settings = load_settings(project_root=tmp_path)

    assert settings.database_url.startswith("sqlite:///")
    assert str(tmp_path) in settings.database_url
    assert settings.poll_interval_seconds == 60
    assert settings.port == 5001
    assert settings.binance.enabled is True
    assert "BTCUSDT" in settings.binance.symbols
    assert settings.criptoya.enabled is True
    assert settings.coingecko.enabled is False
    assert settings.default_channels == ["log"]


def test_toml_overrides(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        """
[poller]
interval_seconds = 15

[server]
host = "0.0.0.0"
port = 8123
dashboard_refresh_seconds = 3
log_level = "debug"

[alerts]
default_cooldown_seconds = 30

[providers.binance]
enabled = true
symbols = ["ETHUSDT"]

[providers.criptoya]
enabled = false
exchanges = ["buenbit", "ripio"]

[notifiers]
default_channels = ["log"]
plugins = ["my_pkg.notifiers:DiscordNotifier"]
""",
        encoding="utf-8",
    )

    settings = load_settings(config_path=config, project_root=tmp_path)

    assert settings.poll_interval_seconds == 15
    assert settings.host == "0.0.0.0"
    assert settings.port == 8123
    assert settings.dashboard_refresh_seconds == 3
    assert settings.log_level == "DEBUG"
    assert settings.default_cooldown_seconds == 30
    assert settings.binance.symbols == ["ETHUSDT"]
    assert settings.criptoya.enabled is False
    assert settings.criptoya.exchanges == ["buenbit", "ripio"]
    assert settings.notifier_plugins == ["my_pkg.notifiers:DiscordNotifier"]


def test_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_POLL_INTERVAL", "20")
    monkeypatch.setenv("CT_PORT", "9000")
    monkeypatch.setenv("CT_HOST", "localhost")
    monkeypatch.setenv("CT_BINANCE_SYMBOLS", "BTCUSDT, SOLUSDT")
    monkeypatch.setenv("CT_CRIPTOYA_EXCHANGES", "buenbit,ripio")
    monkeypatch.setenv("CT_CRIPTOYA_ENABLED", "false")
    monkeypatch.setenv("CT_DATABASE_URL", "sqlite:///custom.db")

    settings = load_settings(project_root=tmp_path)

    assert settings.poll_interval_seconds == 20
    assert settings.port == 9000
    assert settings.host == "localhost"
    assert settings.binance.symbols == ["BTCUSDT", "SOLUSDT"]
    assert settings.criptoya.exchanges == ["buenbit", "ripio"]
    assert settings.criptoya.enabled is False
    assert settings.database_url == "sqlite:///custom.db"


def test_values_are_clamped(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_POLL_INTERVAL", "1")
    monkeypatch.setenv("CT_PORT", "99999")

    settings = load_settings(project_root=tmp_path)
    assert settings.poll_interval_seconds == 5
    assert settings.port == 65535


def test_missing_explicit_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(config_path=tmp_path / "nope.toml", project_root=tmp_path)


def test_empty_default_channels_falls_back_to_log(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("[notifiers]\ndefault_channels = []\n", encoding="utf-8")

    settings = load_settings(config_path=config, project_root=tmp_path)
    assert settings.default_channels == ["log"]
