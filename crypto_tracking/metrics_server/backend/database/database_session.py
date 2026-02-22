from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


class DatabaseSession:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._session: Session | None = None

    def __enter__(self) -> Session:
        SessionLocal = sessionmaker(bind=self.engine)
        self._session = SessionLocal()
        return self._session

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._session is None:
            raise ValueError("Session is not initialized")

        self._session.commit()
        self._session.close()
