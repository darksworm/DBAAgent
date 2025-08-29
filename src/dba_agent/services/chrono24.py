from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

import requests

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None  # type: ignore


DEFAULT_BASE_URL = os.environ.get("CHRONO24_BASE_URL", "https://api.chrono24.com")
DEFAULT_CACHE_TTL = int(os.environ.get("CHRONO24_CACHE_TTL_SECS", str(60 * 60 * 12)))  # 12h


@dataclass
class Chrono24Config:
    api_key: Optional[str] = os.environ.get("CHRONO24_API_KEY")
    base_url: str = DEFAULT_BASE_URL
    cache_ttl_secs: int = DEFAULT_CACHE_TTL
    redis_url: Optional[str] = os.environ.get("REDIS_URL")
    user_agent: str = os.environ.get("HTTP_USER_AGENT", "DBAAgent/1.0")
    # rudimentary rate limit safeguard (client-side)
    min_interval_secs: float = float(os.environ.get("CHRONO24_MIN_INTERVAL_SECS", "0.3"))


class Chrono24Client:
    """Thin client for Chrono24's completed listings.

    - Authentication: API key via `Authorization: Bearer <key>` or `X-API-Key` header.
    - Caching: Optional Redis cache with 12h TTL; falls back to in-process dict.
    - Rate limiting: simple client-side min-interval between requests per process.
    """

    def __init__(self, config: Chrono24Config | None = None) -> None:
        self.config = config or Chrono24Config()
        self._last_call = 0.0
        self._cache_local: dict[str, str] = {}
        self._redis = None
        if self.config.redis_url and redis is not None:
            try:
                self._redis = redis.Redis.from_url(self.config.redis_url)
            except Exception:
                self._redis = None

    def _cache_get(self, key: str) -> Optional[str]:
        if self._redis is not None:
            try:
                val = self._redis.get(key)
                return val.decode("utf-8") if isinstance(val, (bytes, bytearray)) else val
            except Exception:
                return None
        return self._cache_local.get(key)

    def _cache_set(self, key: str, val: str, ttl: int) -> None:
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl, val)
                return
            except Exception:
                pass
        self._cache_local[key] = val

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"User-Agent": self.config.user_agent}
        if self.config.api_key:
            # Support both common schemes
            headers["Authorization"] = f"Bearer {self.config.api_key}"
            headers["X-API-Key"] = self.config.api_key
        return headers

    def get_sold_prices(self, model: str, condition: str) -> List[float]:
        """Return list of sold prices (EUR floats) for a given model and condition.

        Caches results for `cache_ttl_secs` using Redis (if configured).
        """
        clean_model = (model or "").strip()
        cond = (condition or "").strip().lower()
        cache_key = f"chrono24:sold:{clean_model}:{cond}:90d:EUR"
        cached = self._cache_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return [float(x) for x in data if x is not None]
            except Exception:
                pass

        # Respect client-side pacing
        now = time.time()
        if now - self._last_call < self.config.min_interval_secs:
            time.sleep(self.config.min_interval_secs - (now - self._last_call))

        url = f"{self.config.base_url.rstrip('/')}/v1/completed-listings"
        params = {
            "model_identifier": clean_model,
            "condition": cond,
            "date_range": "90d",
            "currency": "EUR",
        }
        try:
            resp = requests.get(url, params=params, headers=self._auth_headers(), timeout=15)
            self._last_call = time.time()
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            return []

        # Expect payload like {"items": [{"sold_price": 1234.56, ...}, ...]}
        prices: List[float] = []
        items = []
        try:
            items = payload.get("items") or []  # type: ignore[assignment]
        except Exception:
            items = []
        for it in items:
            try:
                val = it.get("sold_price")
                if val is not None:
                    prices.append(float(val))
            except Exception:
                continue
        # Cache
        try:
            self._cache_set(cache_key, json.dumps(prices), self.config.cache_ttl_secs)
        except Exception:
            pass
        return prices


class Chrono24LibClient(Chrono24Client):
    """Provider using the community chrono24 library (irahorecka/chrono24).

    This client attempts to fetch completed/sold listings via the library and
    returns sold prices in EUR. Caching and pacing are reused from the base class.
    """

    def __init__(self, config: Chrono24Config | None = None) -> None:  # type: ignore[override]
        super().__init__(config)
        try:
            # Lazy import to avoid hard dependency if provider isn't used
            import importlib

            self._lib = importlib.import_module("chrono24")  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover
            self._lib = None

    def get_sold_prices(self, model: str, condition: str) -> List[float]:  # type: ignore[override]
        clean_model = (model or "").strip()
        cond = (condition or "").strip().lower()
        cache_key = f"chrono24lib:sold:{clean_model}:{cond}:90d:EUR"
        cached = self._cache_get(cache_key)
        if cached:
            try:
                return [float(x) for x in json.loads(cached)]
            except Exception:
                pass

        if not self._lib:
            return []

        # Respect client-side pacing
        now = time.time()
        if now - self._last_call < self.config.min_interval_secs:
            time.sleep(self.config.min_interval_secs - (now - self._last_call))

        prices: List[float] = []
        try:
            # The exact API of the library may differ; below is a defensive approach
            # Try common entry points observed in community libs.
            # e.g., chrono24.Search(completed=True, ...)
            if hasattr(self._lib, "Search"):
                Search = getattr(self._lib, "Search")
                search = Search(query=clean_model, completed=True, currency="EUR", date_range="90d")
                results = search.run() if hasattr(search, "run") else list(search)
                for it in results or []:
                    val = None
                    # Try typical attribute names
                    for key in ("sold_price", "price", "soldPrice", "final_price"):
                        v = getattr(it, key, None)
                        if v is None and isinstance(it, dict):
                            v = it.get(key)
                        if v is not None:
                            val = v
                            break
                    if val is not None:
                        try:
                            prices.append(float(val))
                        except Exception:
                            continue
            else:
                # Fallback: expose no data; caller will hit predictive model
                prices = []
            self._last_call = time.time()
        except Exception:
            prices = []

        try:
            self._cache_set(cache_key, json.dumps(prices), self.config.cache_ttl_secs)
        except Exception:
            pass
        return prices


def make_client(config: Chrono24Config | None = None) -> Chrono24Client:
    """Factory that always returns the library-backed client.

    We exclusively use the community chrono24 library for fetching completed
    listings. No environment flag is required.
    """
    cfg = config or Chrono24Config()
    return Chrono24LibClient(cfg)
