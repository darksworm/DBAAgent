from __future__ import annotations

import os
import re
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    import joblib  # type: ignore
except Exception:  # pragma: no cover
    joblib = None  # type: ignore

from .chrono24 import Chrono24Config, make_client


ALIASES = {
    # Normalization for common Seiko SKX variants
    "skx007k2": "skx007",
    "skx007j": "skx007",
    "skx007": "skx007",
}


def normalize_model(text: str) -> str:
    s = (text or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Heuristic: pick the first token matching a known alias key
    tokens = s.split()
    for i in range(len(tokens)):
        for j in range(i + 1, min(i + 3, len(tokens)) + 1):
            cand = "".join(tokens[i:j])
            if cand in ALIASES:
                return ALIASES[cand]
    # Fallback: longest alnum token
    return max(tokens, key=len) if tokens else s


def eur_to_dkk_rate() -> float:
    try:
        return float(os.environ.get("FX_EUR_TO_DKK", "7.45"))
    except Exception:
        return 7.45


@dataclass
class EstimatorConfig:
    chrono24: Chrono24Config = Chrono24Config()
    model_path: str = os.environ.get("WATCH_RIDGE_MODEL", "models/watch_ridge.pkl")
    min_points: int = 5


class RidgePredictor:
    def __init__(self, model_path: str) -> None:
        self.model_path = model_path
        self._model = None
        if joblib is not None and os.path.exists(model_path):
            try:
                self._model = joblib.load(model_path)  # type: ignore[attr-defined]
            except Exception:
                self._model = None

    def predict(self, title: str, condition: str) -> Optional[float]:
        if not self._model:
            return None
        # Very simple featureization as placeholder: length, has-digit, condition one-hot
        title = (title or "").lower()
        length = len(title)
        has_digit = int(bool(re.search(r"\d", title)))
        cond_idx = {"new": 2, "like-new": 1, "used": 0}.get((condition or "").lower(), 0)
        x = [[length, has_digit, cond_idx]]
        try:
            y = float(self._model.predict(x)[0])
            return y
        except Exception:
            return None


class WatchValueService:
    def __init__(self, cfg: EstimatorConfig | None = None) -> None:
        self.cfg = cfg or EstimatorConfig()
        self.client = make_client(self.cfg.chrono24)
        self.predictor = RidgePredictor(self.cfg.model_path)

    def estimate_resale_dkk(self, title: str, condition: str) -> Optional[float]:
        model = normalize_model(title)
        prices_eur = self.client.get_sold_prices(model, condition)
        if len(prices_eur) >= self.cfg.min_points:
            med = statistics.median(prices_eur)
            return med * eur_to_dkk_rate()
        # fallback to predictor (already expected to output EUR or DKK? define EUR)
        pred_eur = self.predictor.predict(title, condition)
        if pred_eur is not None:
            return pred_eur * eur_to_dkk_rate()
        return None

    def deal_score(self, estimated_resale_dkk: float, listed_price_dkk: float) -> Optional[float]:
        try:
            if estimated_resale_dkk <= 0:
                return None
            return (estimated_resale_dkk - listed_price_dkk) / estimated_resale_dkk
        except Exception:
            return None

    def tag(self, score: Optional[float]) -> Optional[str]:
        if score is None:
            return None
        return "Exceptional" if score >= 0.20 else None
