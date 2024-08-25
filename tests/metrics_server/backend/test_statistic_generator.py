import unittest
from unittest.mock import MagicMock

from sqlalchemy import create_engine

from crypto_tracking.metrics_server.backend.statistics_generator import GetMinMaxValues


class TestStatisticsGenerator(unittest.TestCase):
    def setUp(self):
        self.db_engine = create_engine("sqlite:///:memory:")

    def test_get_min_max_interval(self):
        # Mock the database connection and execute method
        connection_mock = MagicMock()
        connection_mock.execute.return_value = [(10, 100)]  # Mock the result of the query

        # Mock the context manager for the database connection
        db_engine_mock = MagicMock()
        db_engine_mock.connect.return_value.__enter__.return_value = connection_mock

        # Call the function with the mocked objects
        result = GetMinMaxValues(db_engine=db_engine_mock).get_min_max_daily()

        # Assert the result
        self.assertEqual(result, (10, 100))

    def tearDown(self):
        self.db_engine.dispose()


if __name__ == "__main__":
    unittest.main()
