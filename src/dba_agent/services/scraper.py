"""Web scraping utilities built on Scrapy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
import re
import json

import requests
import scrapy
from scrapy import Request
from scrapy.http import Response

from dba_agent.models import Listing


class ListingSpider(scrapy.Spider):
    """Basic spider that extracts ``Listing`` objects from listing cards."""

    name = "listings"
    custom_settings = {
        "DOWNLOAD_DELAY": 0.5,
        "AUTOTHROTTLE_ENABLED": True,
        "RETRY_TIMES": 3,
        # Keep console output clean: don't dump full items with images
        "LOG_LEVEL": "INFO",
        "LOG_FORMATTER": "dba_agent.utils.log.NoItemLogFormatter",
        # Ensure Pydantic models are converted to JSON-serializable dicts
        "ITEM_PIPELINES": {"dba_agent.utils.pipelines.JsonifyPydantic": 100},
    }

    def __init__(
        self,
        start_urls: Optional[Iterable[str] | str] = None,
        max_pages: Optional[int | str] = None,
        stop_before_ts: Optional[str] = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        # Scrapy passes CLI args as strings. Accept either a string (comma/space-separated)
        # or an iterable of strings for start URLs.
        parsed: list[str] = []
        if isinstance(start_urls, str):
            parts = re.split(r"[\s,]+", start_urls.strip()) if start_urls.strip() else []
            parsed = [p for p in parts if p]
        elif start_urls is not None:
            parsed = list(start_urls)
        self.start_urls = parsed
        # Optional limit for pagination depth (for incremental scrapes)
        try:
            self._max_pages = int(max_pages) if max_pages is not None else None
        except Exception:
            self._max_pages = None
        self._pages_seen = 1
        # Optional cutoff timestamp for publish date; if items are sorted newest-first,
        # we can stop pagination as soon as we encounter older items only.
        from datetime import datetime
        self._stop_before: Optional[datetime] = None
        if stop_before_ts:
            try:
                s = stop_before_ts.rstrip('Z')
                self._stop_before = datetime.fromisoformat(s)
            except Exception:
                self._stop_before = None

    def parse(
        self, response: Response, **kwargs: object
    ) -> Iterator[Listing | Request]:
        """Parse listing cards on the page and follow pagination links."""
        yielded = False

        seen_older = False
        for card in response.css("div.listing"):
            yielded = True
            image_urls = card.css("img::attr(src)").getall()
            href = card.css("a::attr(href)").get()
            url = response.urljoin(href) if href else None
            images = [
                data
                for url in image_urls
                if (data := download_image(url)) is not None
            ]
            item = Listing(
                title=card.css("h2::text").get(default="").strip(),
                price=float(card.css("span.price::text").re_first(r"[\d.]+") or 0.0),
                description=card.css("p.description::text").get(),
                images=images,
                location=card.css("span.location::text").get(),
                url=url,
                timestamp=datetime.now(timezone.utc),
            )
            if self._stop_before and item.timestamp <= self._stop_before:
                seen_older = True
                continue
            yield item

        # Fallback: parse JSON-LD ItemList if present (useful for sites like dba.dk)
        if not yielded:
            text = response.text
            idx = text.find('"@type":"ItemList"')
            if idx != -1:
                # Find the enclosing JSON object by matching braces
                start = text.rfind('{', 0, idx)
                end = start
                depth = 0
                for i, ch in enumerate(text[start:], start):
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                blob = text[start:end]
                try:
                    data = json.loads(blob)
                except Exception:
                    data = None
                if isinstance(data, dict) and data.get("@type") == "ItemList":
                    for elem in data.get("itemListElement", []) or []:
                        prod = elem.get("item") if isinstance(elem, dict) else None
                        if not prod and isinstance(elem, dict):
                            prod = elem
                        if not isinstance(prod, dict):
                            continue
                        title = str(prod.get("name") or "").strip()
                        # price might be string; default to 0.0 on failure
                        price_raw = None
                        offers = prod.get("offers") or {}
                        if isinstance(offers, dict):
                            price_raw = offers.get("price")
                        try:
                            price = float(price_raw) if price_raw is not None else 0.0
                        except Exception:
                            price = 0.0
                        desc = prod.get("description") if isinstance(prod.get("description"), str) else None
                        href = prod.get("url") if isinstance(prod.get("url"), str) else None
                        if href and href.startswith("/"):
                            href = response.urljoin(href)
                        imgs = prod.get("image")
                        if isinstance(imgs, list):
                            image_urls = [str(u) for u in imgs]
                        elif isinstance(imgs, str):
                            image_urls = [imgs]
                        else:
                            image_urls = []
                        images = [
                            data
                            for url in image_urls
                            if (data := download_image(url)) is not None
                        ]

                        # Attempt to parse publish date
                        ts = None
                        for key in ("datePublished", "dateModified", "dateCreated"):
                            val = prod.get(key)
                            if isinstance(val, str):
                                try:
                                    ts = datetime.fromisoformat(val.rstrip('Z'))
                                    break
                                except Exception:
                                    pass
                        item = Listing(
                            title=title,
                            price=price,
                            description=desc,
                            images=images,
                            location=None,
                            url=href,
                            timestamp=ts or datetime.now(timezone.utc),
                        )
                        if self._stop_before and item.timestamp <= self._stop_before:
                            seen_older = True
                            continue
                        yield item

        # DBA pagination exposes <a rel="next" href="?page=2&q=...">
        next_page = (
            response.css('nav[aria-label="Pagination"] a[rel="next"]::attr(href)').get()
            or response.css('a[rel="next"]::attr(href)').get()
        )
        if next_page:
            if seen_older and self._stop_before is not None:
                return
            if self._max_pages is None or self._pages_seen < self._max_pages:
                self._pages_seen += 1
                yield response.follow(next_page, callback=self.parse)


def download_image(url: str) -> bytes | None:
    """Download an image and return its bytes.

    Returns ``None`` if the request fails."""

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception:
        return None
    return resp.content


def fetch_dynamic(url: str, wait_time: float = 0.0) -> str:
    """Fetch page HTML using Selenium for sites requiring JS rendering."""

    from selenium import webdriver  # type: ignore[import-not-found]
    from selenium.webdriver.chrome.options import Options  # type: ignore[import-not-found]
    import time

    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        if wait_time:
            time.sleep(wait_time)
        return str(driver.page_source)
    finally:
        driver.quit()
