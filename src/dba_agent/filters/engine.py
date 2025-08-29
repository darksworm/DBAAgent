from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from pydantic import BaseModel

from dba_agent.models import Listing


class FilterConfig(BaseModel):
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    include_keywords: List[str] = []
    exclude_keywords: List[str] = []


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
        # Exclude keywords
        for kw in self._norm(self.config.exclude_keywords):
            if kw in text:
                reasons.append(f"exclude:{kw}")
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

        return FilterResult(True, score, reasons)

    @staticmethod
    def _norm(words: Iterable[str]) -> List[str]:
        return [w.strip().lower() for w in words if w and w.strip()]

