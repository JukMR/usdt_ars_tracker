# USDT/ARS Crypto Tracker

A comprehensive solution for tracking USDT/ARS exchange rate fluctuations from Buenbit, with real-time alerts and notifications.

## Features

- **Automated Price Tracking**: Polls the Buenbit API every 60 seconds for USDT/ARS exchange rates
- **SQLite Database**: Persistent storage of historical price data
- **Price Alerts**: Set minimum/maximum thresholds for buy and sell prices
- **Telegram Notifications**: Real-time alerts sent to Telegram when thresholds are breached
- **Web Interface**: Simple Flask-based UI for managing alerts
- **REST API**: Backend API for programmatic access to metrics and alert management
- **Extensible Notifier System**: Abstract notifier pattern for adding custom notification channels

## Architecture

```
crypto_tracking/
├── api_poller/          # Service that polls exchange rate API
│   └── poller.py
├── metrics_server/      # Flask web application
│   ├── backend/         # API endpoints, alerts, database logic
│   │   ├── database/    # SQLAlchemy models and database service
│   │   └── notifiers/   # Notification implementations (Telegram, Email)
│   └── frontend/        # Web UI templates and routes
├── data/                # SQLite database and CSV exports
└── logs/                # Application logs
```

### Components

1. **API Poller**: Runs continuously, fetching exchange rates from criptoya.com API
2. **Backend Server** (Port 5001): Flask API handling alerts, metrics, and database operations
3. **Frontend Server** (Port 5000): Web interface for setting thresholds and managing alerts
4. **Database Service**: SQLite with SQLAlchemy ORM for data persistence
5. **Notifier System**: Pluggable notification system (Telegram, Email)

## Installation

### Prerequisites

- Python 3.11+
- Poetry (recommended) or pip

### Using Poetry

```bash
# Clone the repository
git clone <repository-url>
cd crypto_tracking

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

### Using pip

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

### Environment Variables

Create a `.env` file in the project root for notifications:

```env
# Telegram Notifications (optional)
BOT_TOKEN=your_telegram_bot_token
CHAT_ID=your_telegram_chat_id

# Email Notifications (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password
RECIPIENT_EMAIL=recipient@example.com
```

**Getting Telegram Credentials:**

1. Create a bot via [@BotFather](https://t.me/botfather) on Telegram
2. Get your bot token from BotFather
3. Add your bot to a group or chat
4. Get the chat ID by sending a message to the group and visiting:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`

**Setting Up Email Notifications:**

1. **Gmail**: Use an [App Password](https://support.google.com/accounts/answer/185833)
2. **Other providers**: Use your SMTP credentials from your email provider
3. Ensure "Less secure app access" is enabled or use app-specific passwords

## Usage

### Running the Services

#### 1. API Poller (Data Collection)

```bash
python -m crypto_tracking.api_poller.poller
```

This starts the continuous polling service that:

- Fetches USDT/ARS rates from Buenbit every 60 seconds
- Stores data in the SQLite database

#### 2. Backend Server (API & Alerts)

```bash
python -m crypto_tracking.metrics_server.backend.backend_main
```

The backend server runs on `http://localhost:5001` and provides:

- Alert checking and notifications
- REST API endpoints

#### 3. Frontend Server (Web UI)

```bash
python -m crypto_tracking.metrics_server.frontend.frontend_main
```

The frontend runs on `http://localhost:5000` and provides:

- Alert threshold configuration
- Alert management interface

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/metrics` | GET | Get current exchange rate |
| `/api/numbers` | POST | Set alert thresholds |
| `/api/alerts` | GET | List all active alerts |
| `/delete/alerts` | DELETE | Delete all alerts |
| `/delete/alert/<id>` | DELETE | Delete specific alert |

### Setting Alerts via API

```bash
curl -X POST http://localhost:5001/api/numbers \
  -H "Content-Type: application/json" \
  -d '{
    "min_num": 1200,
    "max_num": 1300,
    "currency_type": "buy"
  }'
```

### Setting Alerts via Web UI

1. Open `http://localhost:5000`
2. Click "Set Threshold"
3. Enter minimum and/or maximum values
4. Select currency type (buy/sell)
5. Submit to create alerts

## Database

The application uses SQLite with the following schema:

**Table: `entries`**

| Column | Type | Description |
|--------|------|-------------|
| datetime | DateTime | Primary key, timestamp of entry |
| source | String | Data source (e.g., "buenbit") |
| buy | Float | Buy price in ARS |
| sell | Float | Sell price in ARS |

Database file: `crypto_tracking.db` (created automatically in project root)

## Logging

Logs are stored in `logs/` directory with separate files for each log level:

- `debug/` - Debug messages
- `info/` - Informational messages
- `warning/` - Warning messages
- `error/` - Error messages

Log format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

## Development

### Running Tests

```bash
pytest
```

### Code Quality

This project uses:

- **Ruff** for linting and formatting
- **Black** for code formatting (compatible with Ruff)
- **MyPy** for type checking

```bash
# Lint
ruff check .

# Format
ruff format .

# Type check
mypy crypto_tracking/
```

### Project Structure

```
crypto_tracking/
├── crypto_tracking/
│   ├── __init__.py
│   ├── logging_config.py      # Logging configuration
│   ├── csv_handler.py         # CSV export utilities
│   ├── api_poller/
│   │   └── poller.py          # API polling service
│   └── metrics_server/
│       ├── backend/
│       │   ├── backend_main.py
│       │   ├── backend_flask_app.py
│       │   ├── alert_handler.py
│       │   ├── database_utils.py
│       │   ├── statistics_generator.py
│       │   ├── values_model.py
│       │   ├── env_helper.py
│       │   ├── database/
│       │   │   ├── database_service.py
│       │   │   ├── database_session.py
│       │   │   ├── sql_models.py
│       │   │   └── create_database.py
│       │   └── notifiers/
│       │       ├── notifier_abs.py
│       │       ├── telegram_notifier.py
│       │       └── email_notifier.py
│       └── frontend/
│           ├── frontend_main.py
│           └── templates/
│               ├── main.html
│               ├── threshold.html
│               └── alerts.html
├── tests/
├── data/
├── logs/
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Adding Custom Notifiers

To add a new notification channel:

1. Create a new class in `notifiers/` that inherits from `NotifierAbs`
2. Implement the `send_alert(msg: str)` method
3. Register the notifier in `backend_main.py::set_notifiers()`

Example:

```python
from crypto_tracking.metrics_server.backend.notifiers.notifier_abs import NotifierAbs

class CustomNotifier(NotifierAbs):
    def send_alert(self, msg: str) -> None:
        # Your notification logic here
        pass
```

## Troubleshooting

### Database Not Found

- Ensure the API poller has run at least once to create the database
- Check that `crypto_tracking.db` exists in the project root

### Telegram Notifications Not Working

- Verify `BOT_TOKEN` and `CHAT_ID` in `.env`
- Ensure the bot is added to the target chat/group
- Check bot permissions in the group

### Port Already in Use

- Backend (5001): `lsof -i :5001` to find process
- Frontend (5000): `lsof -i :5000` to find process
- Modify ports in `backend_main.py` and `frontend_main.py`

## License

MIT License

## Author

Julian Merida <julianmr97@gmail.com>
