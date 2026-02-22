# Create sql model

from sqlalchemy import Column, DateTime, Float, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Entry(Base):  # type: ignore[valid-type, misc]
    __tablename__ = "entries"
    datetime = Column(DateTime, primary_key=True)
    source = Column(String, nullable=False)
    buy = Column(Float, nullable=False)
    sell = Column(Float, nullable=False)
