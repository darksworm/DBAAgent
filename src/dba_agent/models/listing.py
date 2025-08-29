"""Data models for scraped listings."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class Listing(BaseModel):
    """Represents a single scraped listing from an external site."""

    title: str
    price: float
    description: Optional[str] = None
    image_urls: List[HttpUrl] = Field(default_factory=list)
    location: Optional[str] = None
    timestamp: datetime
