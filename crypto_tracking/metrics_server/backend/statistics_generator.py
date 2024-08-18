from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from sqlalchemy import Engine, text

from crypto_tracking.logging_config import configure_logger


class IntervalTypes(Enum):
    """Enum class for interval types to get min max values"""

    DAILY = 1
    WEEKLY = 7
    TWO_WEEKS = 14
    MONTHLY = 30


def _get_min_max_interval(db_engine: Engine, interval_type: IntervalTypes) -> tuple[int, int]:
    end_date = datetime.now()
    start_date = end_date - timedelta(days=interval_type.value)

    with db_engine.connect() as connection:
        results = connection.execute(
            text("SELECT MIN(sell), MAX(sell) FROM entries WHERE datetime >= :start_date"), {"start_date": start_date}
        )
        for row in results:
            min_val, max_val = row
            return min_val, max_val
    raise ValueError("No values found in the database")


def get_min_max_daily(db_engine: Engine) -> tuple[int, int]:
    return _get_min_max_interval(db_engine, IntervalTypes.DAILY)


def get_min_max_weekly(db_engine: Engine) -> tuple[int, int]:
    return _get_min_max_interval(db_engine, IntervalTypes.WEEKLY)


def get_min_max_two_weeks(db_engine: Engine) -> tuple[int, int]:
    return _get_min_max_interval(db_engine, IntervalTypes.TWO_WEEKS)


def get_min_max_monthly(db_engine: Engine) -> tuple[int, int]:
    return _get_min_max_interval(db_engine, IntervalTypes.MONTHLY)


if __name__ == "__main__":
    from crypto_tracking.metrics_server.backend.database.database_service import DatabaseService

    project_folder = Path(__file__).resolve().parent.parent.parent
    assert project_folder.name == "crypto_tracking", "Project folder is not named 'crypto_tracking'"

    configure_logger(project_folder=project_folder)
    db_engine = DatabaseService(project_folder=project_folder).start()
    print(get_min_max_daily(db_engine))
    print(get_min_max_weekly(db_engine))
    print(get_min_max_two_weeks(db_engine))
    print(get_min_max_monthly(db_engine))
