"""Application configuration.

Configuration is read from, in order of precedence:

1. environment variables (``CT_*`` and notifier credentials),
2. an optional TOML file (``config.toml`` by default),
3. built-in defaults.

Copy ``config.example.toml`` to ``config.toml`` to customise the tracker.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DEFAULT_BINANCE_SYMBOLS = ("BTCUSDT", "ETHUSDT")
DEFAULT_CRIPTOYA_EXCHANGES = ("ripio",)
DEFAULT_COINGECKO_ASSETS = {"bitcoin": "BTC", "ethereum": "ETH"}
DEFAULT_CONFIG_FILENAME = "config.toml"
DEFAULT_POLL_INTERVAL_SECONDS = 60
DEFAULT_DASHBOARD_REFRESH_SECONDS = 10
DEFAULT_COOLDOWN_SECONDS = 3600
DEFAULT_RETENTION_DAYS = 0  # 0 = keep every price row forever


@dataclass(slots=True)
class BinanceConfig:
    enabled: bool = True
    symbols: list[str] = field(default_factory=lambda: list(DEFAULT_BINANCE_SYMBOLS))


@dataclass(slots=True)
class CriptoyaConfig:
    enabled: bool = True
    coin: str = "usdt"
    fiat: str = "ars"
    exchanges: list[str] = field(default_factory=lambda: list(DEFAULT_CRIPTOYA_EXCHANGES))


@dataclass(slots=True)
class CoinGeckoConfig:
    enabled: bool = False
    assets: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_COINGECKO_ASSETS))
    quote_currency: str = "USD"


@dataclass(slots=True)
class Settings:
    """Fully resolved settings for a running tracker instance."""

    project_root: Path
    database_url: str
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS
    host: str = "127.0.0.1"
    port: int = 5001
    debug: bool = False
    log_level: str = "INFO"
    dashboard_refresh_seconds: int = DEFAULT_DASHBOARD_REFRESH_SECONDS
    default_cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS
    retention_days: int = DEFAULT_RETENTION_DAYS
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    criptoya: CriptoyaConfig = field(default_factory=CriptoyaConfig)
    coingecko: CoinGeckoConfig = field(default_factory=CoinGeckoConfig)
    notifier_plugins: list[str] = field(default_factory=list)
    default_channels: list[str] = field(default_factory=lambda: ["log"])


def default_project_root() -> Path:
    """Return the repository root (the parent of the ``crypto_tracking`` package)."""
    return Path(__file__).resolve().parent.parent


def default_database_url(project_root: Path) -> str:
    database_path = project_root / "data" / "crypto_tracking.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{database_path.as_posix()}"


def load_settings(config_path: Path | str | None = None, project_root: Path | str | None = None) -> Settings:
    """Load settings from TOML, environment variables and defaults."""
    root = Path(project_root).resolve() if project_root is not None else default_project_root()
    _load_dotenv(root)

    path, explicit_path = _resolve_config_path(config_path, root)
    data = _read_toml(path, explicit=explicit_path)

    poller_data = data.get("poller", {})
    server_data = data.get("server", {})
    alerts_data = data.get("alerts", {})
    storage_data = data.get("storage", {})
    providers_data = data.get("providers", {})
    notifiers_data = data.get("notifiers", {})

    binance_data = providers_data.get("binance", {})
    binance = BinanceConfig(
        enabled=_as_bool(binance_data.get("enabled", True)),
        symbols=_as_str_list(binance_data.get("symbols", DEFAULT_BINANCE_SYMBOLS), upper=True),
    )

    criptoya_data = providers_data.get("criptoya", {})
    criptoya = CriptoyaConfig(
        enabled=_as_bool(criptoya_data.get("enabled", True)),
        coin=str(criptoya_data.get("coin", "usdt")).lower(),
        fiat=str(criptoya_data.get("fiat", "ars")).lower(),
        exchanges=_as_str_list(criptoya_data.get("exchanges", DEFAULT_CRIPTOYA_EXCHANGES), lower=True),
    )

    coingecko_data = providers_data.get("coingecko", {})
    coingecko_assets = coingecko_data.get("assets", DEFAULT_COINGECKO_ASSETS)
    coingecko = CoinGeckoConfig(
        enabled=_as_bool(coingecko_data.get("enabled", False)),
        assets={str(key).lower(): str(value).upper() for key, value in dict(coingecko_assets).items()},
        quote_currency=str(coingecko_data.get("quote_currency", "USD")).upper(),
    )

    settings = Settings(
        project_root=root,
        database_url=os.environ.get("CT_DATABASE_URL") or default_database_url(root),
        poll_interval_seconds=_as_int(poller_data.get("interval_seconds"), DEFAULT_POLL_INTERVAL_SECONDS, minimum=5),
        host=os.environ.get("CT_HOST") or str(server_data.get("host", "127.0.0.1")),
        port=_as_int(os.environ.get("CT_PORT") or server_data.get("port"), 5001, minimum=1, maximum=65535),
        debug=_as_bool(os.environ.get("CT_DEBUG", server_data.get("debug", False))),
        log_level=(os.environ.get("CT_LOG_LEVEL") or str(server_data.get("log_level", "INFO"))).upper(),
        dashboard_refresh_seconds=_as_int(
            server_data.get("dashboard_refresh_seconds"), DEFAULT_DASHBOARD_REFRESH_SECONDS, minimum=2
        ),
        default_cooldown_seconds=_as_int(
            alerts_data.get("default_cooldown_seconds"), DEFAULT_COOLDOWN_SECONDS, minimum=0
        ),
        retention_days=_as_int(storage_data.get("retention_days"), DEFAULT_RETENTION_DAYS, minimum=0),
        binance=binance,
        criptoya=criptoya,
        coingecko=coingecko,
        notifier_plugins=_as_str_list(notifiers_data.get("plugins", [])),
        default_channels=_as_str_list(notifiers_data.get("default_channels", ["log"]), lower=True),
    )

    _apply_env_overrides(settings)
    _validate(settings)
    return settings


def _resolve_config_path(config_path: Path | str | None, root: Path) -> tuple[Path, bool]:
    if config_path is not None:
        return Path(config_path).expanduser().resolve(), True

    env_path = os.environ.get("CT_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve(), True

    return (root / DEFAULT_CONFIG_FILENAME).resolve(), False


def _read_toml(path: Path, *, explicit: bool) -> dict[str, Any]:
    if not path.exists():
        if explicit:
            raise FileNotFoundError(f"Configuration file not found: {path}")
        return {}

    with path.open("rb") as handle:
        return tomllib.load(handle)


def _load_dotenv(root: Path) -> None:
    env_file = root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


def _apply_env_overrides(settings: Settings) -> None:
    if value := os.environ.get("CT_DATABASE_URL"):
        settings.database_url = value

    if value := os.environ.get("CT_POLL_INTERVAL"):
        settings.poll_interval_seconds = _as_int(value, settings.poll_interval_seconds, minimum=5)

    if value := os.environ.get("CT_DASHBOARD_REFRESH_SECONDS"):
        settings.dashboard_refresh_seconds = _as_int(value, settings.dashboard_refresh_seconds, minimum=2)

    if value := os.environ.get("CT_DEFAULT_COOLDOWN_SECONDS"):
        settings.default_cooldown_seconds = _as_int(value, settings.default_cooldown_seconds, minimum=0)

    if value := os.environ.get("CT_RETENTION_DAYS"):
        settings.retention_days = _as_int(value, settings.retention_days, minimum=0)

    if value := os.environ.get("CT_BINANCE_SYMBOLS"):
        settings.binance.symbols = [part.strip().upper() for part in value.split(",") if part.strip()]

    if (value := os.environ.get("CT_BINANCE_ENABLED")) is not None:
        settings.binance.enabled = _as_bool(value)

    if (value := os.environ.get("CT_CRIPTOYA_ENABLED")) is not None:
        settings.criptoya.enabled = _as_bool(value)

    if value := os.environ.get("CT_CRIPTOYA_COIN"):
        settings.criptoya.coin = value.lower()

    if value := os.environ.get("CT_CRIPTOYA_FIAT"):
        settings.criptoya.fiat = value.lower()

    if value := os.environ.get("CT_CRIPTOYA_EXCHANGES"):
        settings.criptoya.exchanges = [part.strip().lower() for part in value.split(",") if part.strip()]

    if (value := os.environ.get("CT_COINGECKO_ENABLED")) is not None:
        settings.coingecko.enabled = _as_bool(value)


def _validate(settings: Settings) -> None:
    if not settings.database_url:
        raise ValueError("database_url must not be empty")
    if not settings.default_channels:
        settings.default_channels = ["log"]
    if not settings.binance.enabled and not settings.criptoya.enabled and not settings.coingecko.enabled:
        # This is allowed (read-only/offline mode) but worth surfacing early.
        pass


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if value is None or value == "":
        result = default
    else:
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Expected an integer, got: {value!r}") from exc

    if minimum is not None and result < minimum:
        result = minimum
    if maximum is not None and result > maximum:
        result = maximum
    return result


def _as_str_list(value: Any, *, upper: bool = False, lower: bool = False) -> list[str]:
    if value is None:
        items: list[str] = []
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        items = [str(item).strip() for item in value]

    items = [item for item in items if item]
    if upper:
        return [item.upper() for item in items]
    if lower:
        return [item.lower() for item in items]
    return items
