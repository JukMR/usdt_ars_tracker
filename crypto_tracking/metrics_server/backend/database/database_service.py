from pathlib import Path

from sqlalchemy import Engine, create_engine

from crypto_tracking.logging_config import logger
from crypto_tracking.metrics_server.backend.database.create_database import DatabasePopulator
from crypto_tracking.metrics_server.backend.database.sql_models import Base

DB_NAME: str = "crypto_tracking.db"


class DatabaseService:
    """Database service class."""

    def __init__(self, project_folder: Path) -> None:
        self.project_folder: Path = project_folder
        self.database_path: Path = self.project_folder / DB_NAME

    def _database_exists(self) -> bool:
        return self.database_path.exists()

    def _create_database(self) -> Engine:
        """Create the database and tables"""

        engine = self._get_database()
        Base.metadata.create_all(engine)

        # Populate db with csv file

        DatabasePopulator(project_folder=self.project_folder, db_engine=engine).populate_database()

        return engine

    def _get_database(self) -> Engine:
        """Get the database engine."""
        return create_engine(f"sqlite:///{self.database_path}")

    def start(self) -> Engine:
        """Start the database service."""
        if not self._database_exists():
            logger.info("Database does not exist. Creating a new one...")
            self._create_database()
        else:
            logger.info("Database already exists. Connecting to it...")

        return self._get_database()
