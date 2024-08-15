import os

from sqlalchemy import MetaData, Table, create_engine
from sqlalchemy.exc import OperationalError

from crypto_tracking.metrics_server.backend.database.migrate_to_database import create_database

DB_NAME: str = "crypto_tracking.db"


def database_exists() -> bool:
    """Check if the database and table 'entry' exist."""
    engine = create_engine(f"sqlite:///{DB_NAME}")
    try:
        metadata = MetaData(bind=engine)
        entry_table: Table = Table("entry", metadata, autoload_with=engine)
        return True

    except OperationalError:
        return False


def run_database() -> None:
    """Simulate starting the database service."""
    # SQLite is a file-based database, so no service needs to be started.
    # But if you have additional services or tasks, you can handle them here.
    if not os.path.exists(DB_NAME):
        raise FileNotFoundError(f"Database '{DB_NAME}' not found.")
    print("Database is ready for use")


def start():
    """Check if the database exists and start it."""
    if not database_exists():
        create_database()
    else:
        print("Database already exists")

    run_database()


if __name__ == "__main__":
    start()
