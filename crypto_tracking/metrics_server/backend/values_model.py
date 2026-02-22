from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class Values(BaseModel):
    """Values model for entries"""

    timestamp: datetime
    source: str
    buy: float
    sell: float

    # Transform custom datetime into datetime
    @field_validator("timestamp", mode="before")
    @classmethod
    def transform(cls, raw: Any) -> datetime:
        if isinstance(raw, datetime):
            return raw
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f")
