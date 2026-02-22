"""Integration tests for database operations and alert handling."""

import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine, text

from crypto_tracking.metrics_server.backend.alert_handler import (
    Alert,
    Alerter,
    CurrencyType,
    Operators,
)
from crypto_tracking.metrics_server.backend.database.create_database import (
    DatabaseFromCSVPopulator,
)
from crypto_tracking.metrics_server.backend.database.database_session import (
    DatabaseSession,
)
from crypto_tracking.metrics_server.backend.database.sql_models import Base, Entry
from crypto_tracking.metrics_server.backend.values_model import Values


class TestDatabaseOperations(unittest.TestCase):
    """Test database operations including CRUD and CSV population."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.test_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.test_engine)

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        self.test_engine.dispose()

    def test_insert_entry(self) -> None:
        """Test inserting a single entry into the database."""
        with DatabaseSession(engine=self.test_engine) as session:
            entry = Entry(
                datetime=datetime.now(),
                source="buenbit",
                buy=1200.50,
                sell=1180.25,
            )
            session.add(entry)

        with self.test_engine.connect() as connection:
            result = connection.execute(text("SELECT COUNT(*) FROM entries"))
            count = result.scalar()
            self.assertEqual(count, 1)

    def test_insert_multiple_entries(self) -> None:
        """Test inserting multiple entries into the database."""
        entries = [
            Entry(datetime=datetime.now() - timedelta(hours=i), source="buenbit", buy=1200.0 + i, sell=1180.0 + i)
            for i in range(5)
        ]

        with DatabaseSession(engine=self.test_engine) as session:
            for entry in entries:
                session.add(entry)

        with self.test_engine.connect() as connection:
            result = connection.execute(text("SELECT COUNT(*) FROM entries"))
            count = result.scalar()
            self.assertEqual(count, 5)

    def test_query_latest_entry(self) -> None:
        """Test querying the latest entry from the database."""
        now = datetime.now()
        entries = [
            Entry(datetime=now - timedelta(hours=2), source="buenbit", buy=1200.0, sell=1180.0),
            Entry(datetime=now - timedelta(hours=1), source="buenbit", buy=1210.0, sell=1190.0),
            Entry(datetime=now, source="buenbit", buy=1220.0, sell=1200.0),
        ]

        with DatabaseSession(engine=self.test_engine) as session:
            for entry in entries:
                session.add(entry)

        with self.test_engine.connect() as connection:
            result = connection.execute(text("SELECT * FROM entries ORDER BY datetime DESC LIMIT 1"))
            row = result.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[2], 1220.0)  # buy price

    def test_csv_population(self) -> None:
        """Test populating database from CSV file."""
        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            data_folder = tmpdir_path / "data"
            data_folder.mkdir()

            csv_file = data_folder / "exchange_rates.csv"
            csv_file.write_text(
                "timestamp,source,buy,sell\n"
                "2024-01-01 10:00:00.000000,buenbit,1200.50,1180.25\n"
                "2024-01-01 11:00:00.000000,buenbit,1205.75,1185.50\n"
                "2024-01-01 12:00:00.000000,buenbit,1210.00,1190.00\n"
            )

            populator = DatabaseFromCSVPopulator(project_folder=tmpdir_path, db_engine=self.test_engine)
            populator.populate_database()

            with self.test_engine.connect() as connection:
                result = connection.execute(text("SELECT COUNT(*) FROM entries"))
                count = result.scalar()
                self.assertEqual(count, 3)


class TestAlertHandler(unittest.TestCase):
    """Test alert handling logic including threshold checks and notifications."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.alerter = Alerter()

    def test_alert_less_than_threshold(self) -> None:
        """Test alert triggers when value is less than threshold."""
        alert = Alert(currency="USDT", currency_type=CurrencyType.BUY, threshold=1200.0, operator=Operators.LESS_THAN)
        self.alerter.add_alert(alert, notifiers=[])

        data_below = Values(timestamp=datetime.now(), source="buenbit", buy=1150.0, sell=1130.0)
        data_above = Values(timestamp=datetime.now(), source="buenbit", buy=1250.0, sell=1230.0)

        self.assertTrue(alert.check(data_below))
        self.assertFalse(alert.check(data_above))

    def test_alert_greater_than_threshold(self) -> None:
        """Test alert triggers when value is greater than threshold."""
        alert = Alert(
            currency="USDT", currency_type=CurrencyType.SELL, threshold=1200.0, operator=Operators.GREATER_THAN
        )
        self.alerter.add_alert(alert, notifiers=[])

        data_below = Values(timestamp=datetime.now(), source="buenbit", buy=1150.0, sell=1150.0)
        data_above = Values(timestamp=datetime.now(), source="buenbit", buy=1250.0, sell=1250.0)

        self.assertFalse(alert.check(data_below))
        self.assertTrue(alert.check(data_above))

    def test_alert_equal_threshold(self) -> None:
        """Test alert triggers when value equals threshold."""
        alert = Alert(currency="USDT", currency_type=CurrencyType.BUY, threshold=1200.0, operator=Operators.EQUAL)
        self.alerter.add_alert(alert, notifiers=[])

        data_equal = Values(timestamp=datetime.now(), source="buenbit", buy=1200.0, sell=1180.0)
        data_different = Values(timestamp=datetime.now(), source="buenbit", buy=1201.0, sell=1181.0)

        self.assertTrue(alert.check(data_equal))
        self.assertFalse(alert.check(data_different))

    def test_alert_delete(self) -> None:
        """Test deleting alerts."""
        alert1 = Alert(currency="USDT", currency_type=CurrencyType.BUY, threshold=1200.0, operator=Operators.LESS_THAN)
        alert2 = Alert(currency="USDT", currency_type=CurrencyType.SELL, threshold=1300.0, operator=Operators.GREATER_THAN)

        self.alerter.add_alert(alert1, notifiers=[])
        self.alerter.add_alert(alert2, notifiers=[])

        alerts = self.alerter.get_alerts()
        self.assertEqual(len(alerts), 2)

        self.alerter.delete_alert(0)
        alerts = self.alerter.get_alerts()
        self.assertEqual(len(alerts), 1)

        self.alerter.delete_all_alerts()
        alerts = self.alerter.get_alerts()
        self.assertEqual(len(alerts), 0)

    def test_alert_to_json(self) -> None:
        """Test alert JSON serialization."""
        alert = Alert(currency="USDT", currency_type=CurrencyType.BUY, threshold=1200.0, operator=Operators.LESS_THAN)
        json_data = alert.to_json()

        self.assertEqual(json_data["currency"], "USDT")
        self.assertEqual(json_data["currency_type"], "BUY")
        self.assertEqual(json_data["threshold"], 1200.0)
        self.assertEqual(json_data["operator"], "<")
        self.assertEqual(json_data["alert_notifiers"], [])

    def test_check_alerts(self) -> None:
        """Test checking multiple alerts against data."""
        alert_triggered = []

        class MockNotifier:
            def send_alert(self, msg: str) -> None:
                alert_triggered.append(msg)

        alert = Alert(currency="USDT", currency_type=CurrencyType.BUY, threshold=1200.0, operator=Operators.LESS_THAN)
        self.alerter.add_alert(alert, notifiers=[MockNotifier()])

        data = Values(timestamp=datetime.now(), source="buenbit", buy=1150.0, sell=1130.0)

        with patch("crypto_tracking.metrics_server.backend.alert_handler.read_latest_value", return_value=data):
            self.alerter.check_alerts(data)

        self.assertEqual(len(alert_triggered), 1)
        self.assertIn("1150.0", alert_triggered[0])


class TestValuesModel(unittest.TestCase):
    """Test Values Pydantic model validation."""

    def test_values_from_datetime(self) -> None:
        """Test Values model accepts datetime objects."""
        now = datetime.now()
        values = Values(timestamp=now, source="buenbit", buy=1200.0, sell=1180.0)
        self.assertEqual(values.timestamp, now)

    def test_values_from_string(self) -> None:
        """Test Values model parses string timestamps."""
        values = Values(
            timestamp="2024-01-01 12:00:00.000000",
            source="buenbit",
            buy=1200.0,
            sell=1180.0,
        )
        self.assertEqual(values.timestamp.year, 2024)
        self.assertEqual(values.timestamp.month, 1)
        self.assertEqual(values.timestamp.day, 1)
        self.assertEqual(values.timestamp.hour, 12)

    def test_values_validation(self) -> None:
        """Test Values model validates required fields."""
        with self.assertRaises(Exception):
            Values(timestamp=datetime.now(), buy=1200.0, sell=1180.0)  # type: ignore


if __name__ == "__main__":
    unittest.main()
