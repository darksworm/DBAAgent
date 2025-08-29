from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from pydantic import BaseModel
from datetime import datetime, timedelta, timezone

from dba_agent.models import Listing


class FilterConfig(BaseModel):
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    include_keywords: List[str] = []
    exclude_keywords: List[str] = []
    location_includes: List[str] = []
    location_excludes: List[str] = []
    min_images: Optional[int] = None
    max_age_days: Optional[int] = None


@dataclass
class FilterResult:
    included: bool
    score: float
    reasons: List[str]


class FilterEngine:
    """Apply simple boolean rules and compute a naive score."""

    def __init__(self, config: FilterConfig) -> None:
        self.config = config

    def apply(self, listing: Listing) -> FilterResult:
        score = 0.0
        reasons: List[str] = []

        # Price band
        if self.config.min_price is not None:
            if listing.price < self.config.min_price:
                reasons.append("price_below_min")
                return FilterResult(False, score, reasons)
            score += 0.5
        if self.config.max_price is not None:
            if listing.price > self.config.max_price:
                reasons.append("price_above_max")
                return FilterResult(False, score, reasons)
            score += 0.5

        text = f"{listing.title} {listing.description or ''}".lower()
        loc = (listing.location or "").lower()
        # Exclude keywords
        for kw in self._norm(self.config.exclude_keywords):
            if kw in text:
                reasons.append(f"exclude:{kw}")
                return FilterResult(False, score, reasons)
        for kw in self._norm(self.config.location_excludes):
            if kw and kw in loc:
                reasons.append(f"exclude_loc:{kw}")
                return FilterResult(False, score, reasons)

        # Include keywords
        matched_includes = 0
        for kw in self._norm(self.config.include_keywords):
            if kw and kw in text:
                matched_includes += 1
        if self.config.include_keywords and matched_includes == 0:
            reasons.append("no_include_keywords_matched")
            return FilterResult(False, score, reasons)
        score += matched_includes

        # Location includes (soft requirement if provided)
        if self.config.location_includes:
            if any(kw in loc for kw in self._norm(self.config.location_includes)):
                score += 0.5
            else:
                reasons.append("no_location_include_matched")
                return FilterResult(False, score, reasons)

        # Minimum number of images
        if self.config.min_images is not None:
            if len(listing.image_urls) < self.config.min_images:
                reasons.append("below_min_images")
                return FilterResult(False, score, reasons)
            score += 0.5

        # Max age days
        if self.config.max_age_days is not None:
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(days=self.config.max_age_days)
                if listing.timestamp < cutoff:
                    reasons.append("too_old")
                    return FilterResult(False, score, reasons)
                score += 0.5
            except Exception:
                pass

        return FilterResult(True, score, reasons)

    @staticmethod
    def _norm(words: Iterable[str]) -> List[str]:
        return [w.strip().lower() for w in words if w and w.strip()]
