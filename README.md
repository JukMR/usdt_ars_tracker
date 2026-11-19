# Crypto Tracker

A local, multi-source cryptocurrency price tracker with a near-live dashboard,
persistent threshold alerts and pluggable notification channels.

It is built to sit next to TradingView rather than replace it: the dashboard
gives you a lightweight, offline-friendly view of the pairs and venues *you*
care about (including USDT/ARS in Argentina), keeps a local history in SQLite,
and sends alerts to Telegram, email or any channel you add.

## Features

- **Multiple assets and venues** — track BTC, ETH, SOL, USDT and anything else
  your providers expose. Quotes are stored as `asset / quote_currency / source`,
  so the same pair can be compared across exchanges.
- **Near-live dashboard** — Flask + Chart.js, polling the local API every few
  seconds. Chart.js is vendored, so the UI also works without internet access.
- **Min/max threshold alerts** — operators `<`, `<=`, `=`, `>`, `>=` over
  `price`, `bid` or `ask`. Alerts are edge-triggered, re-arm when the condition
  becomes false, and support cooldowns plus optional repeating.
- **Persistent history** — every fetch is written to SQLite. Alert events and
  per-channel delivery results are kept too, so you can audit what fired and
  whether it was delivered.
- **Pluggable notifiers** — built-in `log`, `telegram` and `email` channels,
  plus dynamic loading of your own classes.
- **Offline mode** — serve the dashboard from existing local data with
  `crypto-track serve --no-poller`.
- **CSV import/export** — bring in legacy `timestamp,source,buy,sell` files or
  export the full history.
- **TradingView links** — each pair card links out to TradingView for deeper
  charting and indicators.

## Quick start

Install [uv](https://docs.astral.sh/uv/) if you do not have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then clone the project and let uv create the virtual environment and install
the locked dependencies:

```bash
git clone <repository-url>
cd crypto_tracking
uv sync

# Optional: customise providers, ports and intervals.
cp config.example.toml config.toml

# Fetch one round and evaluate alerts.
uv run crypto-track poll --once

# Poll continuously, evaluate alerts and serve the dashboard.
uv run crypto-track serve
```

Open <http://127.0.0.1:5001/>.

`uv run` executes the `crypto-track` script inside the project environment
without activating it. If you prefer an activated shell, use `source
.venv/bin/activate` after `uv sync` and then call `crypto-track` directly.

## How it works

```
providers ──► poller ──► SQLite ◄── alert engine ──► notifiers
                           ▲              │
                           └──── web/API ─┘
```

| Layer | Package | Responsibility |
| --- | --- | --- |
| Domain | `crypto_tracking/domain.py` | `Quote`, `PriceStats`, `Notification`, metrics, operators, time helpers |
| Config | `crypto_tracking/config.py` | TOML + environment settings |
| Providers | `crypto_tracking/providers/` | Binance, Criptoya, CoinGecko; one `fetch()` per source |
| Storage | `crypto_tracking/storage/` | SQLAlchemy models, database session, repositories |
| Alerts | `crypto_tracking/alerts/` | Threshold evaluation, cooldown/re-arm logic, message formatting |
| Notifiers | `crypto_tracking/notifiers/` | Registry, `log`, `telegram`, `email`, plugin loading |
| Web | `crypto_tracking/web/` | Dashboard template/assets and JSON API |
| CLI | `crypto_tracking/cli.py` | `serve`, `poll`, `check`, `status`, CSV tools |

Prices enter the system as an immutable `Quote`; nothing provider-specific or
database-specific leaks into the alert or web layers. That is what makes new
exchanges and new notification channels small, isolated additions.

## Configuration

Configuration is resolved in this order (later wins):

1. built-in defaults,
2. `config.toml` in the project root (or `--config PATH`),
3. environment variables, including `.env`.

Start from `config.example.toml` and `.env.example`.

```toml
[poller]
interval_seconds = 60

[server]
host = "127.0.0.1"
port = 5001
debug = false
dashboard_refresh_seconds = 10
log_level = "INFO"

[alerts]
default_cooldown_seconds = 3600

[providers.binance]
enabled = true
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

[providers.criptoya]
enabled = true
coin = "usdt"
fiat = "ars"
# Empty list = every venue criptoya returns.
exchanges = ["ripio"]

[providers.coingecko]
enabled = false
quote_currency = "USD"

[notifiers]
plugins = []
default_channels = ["log"]
```

### Environment overrides

| Variable | Example | Purpose |
| --- | --- | --- |
| `CT_CONFIG` | `/etc/ct/config.toml` | Config file path |
| `CT_DATABASE_URL` | `sqlite:///data/ct.db` | SQLAlchemy database URL |
| `CT_HOST` / `CT_PORT` | `0.0.0.0` / `5001` | Dashboard bind address |
| `CT_DEBUG` | `true` | Flask debug mode |
| `CT_LOG_LEVEL` | `DEBUG` | Logging level |
| `CT_POLL_INTERVAL` | `30` | Seconds between polls (min 5) |
| `CT_DASHBOARD_REFRESH_SECONDS` | `5` | Browser refresh interval (min 2) |
| `CT_BINANCE_ENABLED` | `true` | Enable Binance |
| `CT_BINANCE_SYMBOLS` | `BTCUSDT,ETHUSDT` | Binance symbols |
| `CT_CRIPTOYA_ENABLED` | `true` | Enable Criptoya |
| `CT_CRIPTOYA_COIN` / `CT_CRIPTOYA_FIAT` | `usdt` / `ars` | Criptoya pair |
| `CT_CRIPTOYA_EXCHANGES` | `ripio,letsbit` | Venues to record |
| `CT_COINGECKO_ENABLED` | `true` | Enable CoinGecko fallback |

### Notification credentials

Telegram:

```bash
BOT_TOKEN=123456789:AA...
CHAT_ID=-100...
```

Email (SMTP):

```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SENDER_EMAIL=you@example.com
SENDER_PASSWORD=your_app_password
RECIPIENT_EMAIL=you@example.com,alerts@example.com
```

A channel whose credentials are missing is skipped with a warning at start-up;
the rest keep working. `log` is always available.

## Providers

| Provider | Pairs | Notes |
| --- | --- | --- |
| `binance` | Any `<ASSET><QUOTE>` symbol, e.g. `BTCUSDT` | Uses `/api/v3/ticker/24hr`; splits symbols into asset/quote automatically |
| `criptoya` | `USDT/ARS` (configurable coin/fiat) | Aggregates Argentine exchanges; records one source per venue, e.g. `criptoya:ripio` |
| `coingecko` | `BTC/USD`, `ETH/USD`, … | Disabled by default; useful as a USD fallback |

### Adding a provider

Implement `PriceProvider` and register it in
`crypto_tracking/providers/registry.py`:

```python
from crypto_tracking.domain import Quote
from crypto_tracking.providers.base import PriceProvider


class MyExchangeProvider(PriceProvider):
    name = "my-exchange"

    def pairs(self) -> list[tuple[str, str]]:
        return [("BTC", "USD")]

    def fetch(self) -> list[Quote]:
        # Fetch data, then normalise it:
        return [
            Quote(
                asset="BTC",
                quote_currency="USD",
                source=self.name,
                price=62_000.0,
                bid=61_999.0,
                ask=62_001.0,
            )
        ]
```

The poller calls `fetch()` on every enabled provider; a failure in one provider
does not stop the others.

## Alerts

Alerts are stored in SQLite and evaluated after every poll (and via
`POST /api/check`).

- **Metric**: `price`, `bid` or `ask`.
- **Operator**: `<`, `<=`, `=`, `>`, `>=`.
- **Source** (optional): pin the alert to one venue, e.g. `criptoya:ripio`.
  Leave empty to use the latest quote across all sources for that pair.
- **Channels**: any registered notifier (`log`, `telegram`, `email`, plugins).
- **Edge-triggered by default**: fires on the transition from "condition false"
  to "condition true". Once the condition is false again, the alert re-arms.
- **Cooldown**: suppresses re-firing during the configured window.
- **Repeat**: when enabled, fires again every cooldown while the condition
  stays true.

Every trigger creates an `alert_event` row and one `alert_delivery` row per
channel, including failures and their error messages. Events and deliveries
remain even if the alert is later deleted.

Create alerts from the dashboard or the API:

```bash
curl -X POST http://127.0.0.1:5001/api/alerts \
  -H 'Content-Type: application/json' \
  -d '{
    "asset": "BTC",
    "quote_currency": "USDT",
    "metric": "price",
    "operator": ">",
    "threshold": 70000,
    "channels": ["log", "telegram"],
    "cooldown_seconds": 900,
    "repeat": false,
    "label": "BTC breakout"
  }'
```

### Custom notifiers

Subclass `Notifier`, implement `send()`, and reference the class in
`config.toml` using `module:Class` or `module.Class`:

```python
# my_project/notifiers.py
from crypto_tracking.domain import Notification
from crypto_tracking.notifiers.base import Notifier


class DiscordNotifier(Notifier):
    channel = "discord"

    def send(self, notification: Notification) -> None:
        # Send notification.title / notification.message somewhere.
        ...
```

```toml
[notifiers]
plugins = ["my_project.notifiers:DiscordNotifier"]
default_channels = ["log", "discord"]
```

`send()` should raise on failure. The engine catches the exception, records a
failed delivery and continues with the remaining channels.

## Dashboard

The dashboard at `/` includes:

- price cards per pair with latest price, bid/ask, window low/high, source and
  freshness, plus a TradingView link;
- a Chart.js line chart with one series per source and selectable ranges
  (`1h`, `6h`, `24h`, `7d`, `30d`, `all`);
- an alert form (pair, metric, operator, threshold, source, channels, cooldown,
  repeat, label);
- an alert table with enable/disable toggles and delete buttons;
- a recent-events table showing delivery success/failure per channel;
- manual refresh, pause/resume live polling, and an "Check now" action.

## CLI

Run these with `uv run` (for example `uv run crypto-track serve`) or after
activating the environment with `source .venv/bin/activate`.

```bash
crypto-track serve                 # poller + alert engine + dashboard
crypto-track serve --no-poller     # dashboard only, from local data
crypto-track serve --offline       # alias for --no-poller
crypto-track serve --host 0.0.0.0 --port 8080 --debug
crypto-track poll                  # poller only, runs forever
crypto-track poll --once           # one fetch + one alert evaluation
crypto-track check                 # evaluate alerts once, print events
crypto-track status                # database, providers, notifiers, pairs
crypto-track init-db               # create tables and print counts
crypto-track import-csv PATH       # import legacy or modern CSV
crypto-track export-csv PATH       # export history
```

CSV import accepts both layouts:

```csv
timestamp,source,buy,sell
2024-07-28 12:47:18,buenbit,1342.92,1327.0
```

```csv
timestamp,asset,quote_currency,source,price,bid,ask,volume
2024-01-01T00:00:00Z,BTC,USDT,binance,62000,61999,62001,10
```

Legacy `buy` maps to `ask` and `sell` maps to `bid`; the stored `price` is their
midpoint when no explicit price column exists.

## HTTP API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Dashboard |
| `GET` | `/api/health` | Status, row counts |
| `GET` | `/api/config` | Pairs, ranges, providers, notifiers |
| `GET` | `/api/notifiers` | Registered channels and classes |
| `GET` | `/api/overview?range=24h` | Latest price + stats per pair |
| `GET` | `/api/prices/latest` | Latest row per source |
| `GET` | `/api/prices/history?asset=BTC&quote_currency=USDT&range=24h&max_points=800` | Chart points |
| `GET` | `/api/prices/stats?asset=BTC&quote_currency=USDT&range=24h` | Aggregate stats |
| `GET` | `/api/prices/export.csv` | CSV download |
| `GET` | `/api/alerts` | List alerts |
| `POST` | `/api/alerts` | Create an alert |
| `PATCH` | `/api/alerts/<id>` | Update fields (including `enabled`) |
| `DELETE` | `/api/alerts/<id>` | Delete one alert |
| `DELETE` | `/api/alerts` | Delete all alerts |
| `GET` | `/api/events?limit=50` | Alert events with deliveries |
| `POST` | `/api/check` | Evaluate alerts once |

Legacy routes are kept for existing scripts: `GET /metrics`,
`POST /api/numbers`, `DELETE /delete/alerts`, `DELETE /delete/alert/<id>`, and
redirects at `/alerts` and `/threshold`.

## Database

SQLite by default at `data/crypto_tracking.db` (`data/` is git-ignored).

- `prices` — every quote, unique on `(asset, quote_currency, source, timestamp)`.
- `alerts` — metric, operator, threshold, optional source, channels JSON,
  cooldown, repeat flag, enabled flag, last state and last trigger time.
- `alert_events` — snapshot of each trigger; `alert_id` becomes `NULL` if the
  alert is deleted.
- `alert_deliveries` — one row per channel attempt, with success/error.

## Offline analysis

Stop the poller and keep exploring what you already collected:

```bash
uv run crypto-track serve --no-poller
```

The dashboard, chart, alerts and CSV export all read from the local database.
`uv run crypto-track export-csv history.csv --range all` produces a portable
snapshot for spreadsheets or notebooks.

## Development

```bash
uv sync                  # create/update .venv from uv.lock (includes dev tools)
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy crypto_tracking
```

Use `uv add <package>` and `uv remove <package>` to change dependencies; uv
updates `pyproject.toml` and `uv.lock` together. `uv lock --upgrade` refreshes
the lock file without changing version constraints.

Tests use temporary SQLite files and fake HTTP sessions/notifiers, so they never
touch the network or your real database.

## Project layout

```
crypto_tracking/
├── alerts/          # evaluation engine and message formatting
├── notifiers/       # base class, log/telegram/email, plugin registry
├── providers/       # Binance, Criptoya, CoinGecko, registry
├── storage/         # SQLAlchemy models, database, repositories
├── web/
│   ├── app.py
│   ├── templates/dashboard.html
│   └── static/      # style.css, app.js, vendor/chart.umd.min.js
├── cli.py
├── config.py
├── domain.py
├── importer.py
└── poller.py
tests/
config.example.toml
.env.example
```

## TradingView

TradingView does not offer a reliable public historical-price API, so this
project does not scrape it. Instead:

- prices come from exchange/public APIs (Binance, Criptoya, CoinGecko);
- each pair in the dashboard links to its TradingView symbol for indicators,
  drawings and multi-timeframe analysis;
- local history is available for offline inspection and CSV export.

That keeps the tracker fast and dependable while complementing TradingView
rather than duplicating it.

## Troubleshooting

- **`No prices yet`** — run `uv run crypto-track poll --once`, or check provider
  warnings in the logs.
- **Telegram/email warnings** — set the credentials in `.env`; only configured
  channels are registered.
- **Port already in use** — change `server.port` or pass `--port`.
- **Criptoya venue missing** — the exchange may have left the aggregator; run
  with `exchanges = []` to record every venue returned, or choose another name.
- **Empty chart** — select a pair that has data and a range that covers its
  timestamps. The dashboard defaults to `24h`.

## License

MIT
