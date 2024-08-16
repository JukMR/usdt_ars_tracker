from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker


class DatabaseSession:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.session = None

    def __enter__(self) -> Any:
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.session.commit()
        self.session.close()
