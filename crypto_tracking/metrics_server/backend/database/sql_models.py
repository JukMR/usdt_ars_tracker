# Create sql model

from sqlalchemy import Column, DateTime, Float, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Entry(Base):
    __tablename__ = "entries"
    datetime = Column(DateTime, primary_key=True)
    source = Column(String, nullable=False)
    buy = Column(Float, nullable=False)
    sell = Column(Float, nullable=False)
