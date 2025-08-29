from __future__ import annotations

import math

from dba_agent.services.watch_value import normalize_model, WatchValueService, EstimatorConfig
from dba_agent.services.chrono24 import Chrono24Client, Chrono24Config


class FakeChrono24(Chrono24Client):
    def __init__(self, prices):
        super().__init__(Chrono24Config(api_key=None, redis_url=None))
        self._prices = prices

    def get_sold_prices(self, model: str, condition: str):
        return list(self._prices)


def test_normalize_model_aliases():
    assert normalize_model("Seiko SKX007K2 Diver") == "skx007"
    assert normalize_model("skx007j") == "skx007"


def test_estimate_with_median(monkeypatch):
    svc = WatchValueService(EstimatorConfig())
    svc.client = FakeChrono24([100, 200, 300, 400, 1000])  # 5 points => median=300
    # Force fx rate
    monkeypatch.setenv("FX_EUR_TO_DKK", "7.5")
    est = svc.estimate_resale_dkk("Seiko SKX007K2", "used")
    assert est is not None
    assert math.isclose(est, 300 * 7.5, rel_tol=1e-6)


def test_deal_score_and_tag():
    svc = WatchValueService(EstimatorConfig())
    score = svc.deal_score(estimated_resale_dkk=1500, listed_price_dkk=1200)
    assert score is not None
    assert round(score, 2) == 0.2
    assert svc.tag(score) == "Exceptional"
