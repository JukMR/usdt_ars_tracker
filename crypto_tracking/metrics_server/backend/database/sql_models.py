# Create sql model

from sqlalchemy import Column, Date, Float, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Entry(Base):
    __tablename__ = "entries"
    date = Column(Date, nullable=False)
    source = Column(String, nullable=False)
    buy = Column(Float, nullable=False)
    sell = Column(Float, nullable=False)
