from datetime import datetime

from pydantic import BaseModel


class Values(BaseModel):
    timestamp: datetime
    source: str
    buy: float
    sell: float
