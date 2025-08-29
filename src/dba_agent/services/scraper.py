"""Web scraping utilities built on Scrapy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
import re
import json

import scrapy
from scrapy import Request
from scrapy.http import Response

from dba_agent.models import Listing


class ListingSpider(scrapy.Spider):  # type: ignore[misc]
    """Basic spider that extracts ``Listing`` objects from listing cards."""

    name = "listings"
    custom_settings = {
        "DOWNLOAD_DELAY": 0.5,
        "AUTOTHROTTLE_ENABLED": True,
        "RETRY_TIMES": 3,
        # Ensure Pydantic models are converted to JSON-serializable dicts
        "ITEM_PIPELINES": {"dba_agent.utils.pipelines.JsonifyPydantic": 100},
    }

    def __init__(
        self, start_urls: Optional[Iterable[str] | str] = None, **kwargs: object
    ) -> None:
        super().__init__(**kwargs)
        # Scrapy passes CLI args as strings. Accept either a string (comma/space-separated)
        # or an iterable of strings for start URLs.
        parsed: list[str] = []
        if isinstance(start_urls, str):
            parts = re.split(r"[\s,]+", start_urls.strip()) if start_urls.strip() else []
            parsed = [p for p in parts if p]
        elif start_urls is not None:
            parsed = list(start_urls)
        self.start_urls = parsed

    def parse(
        self, response: Response, **kwargs: object
    ) -> Iterator[Listing | Request]:
        """Parse listing cards on the page and follow pagination links."""
        yielded = False

        for card in response.css("div.listing"):
            yielded = True
            item = Listing(
                title=card.css("h2::text").get(default="").strip(),
                price=float(card.css("span.price::text").re_first(r"[\d.]+") or 0.0),
                description=card.css("p.description::text").get(),
                image_urls=card.css("img::attr(src)").getall(),
                location=card.css("span.location::text").get(),
                timestamp=datetime.now(timezone.utc),
            )
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
                        imgs = prod.get("image")
                        if isinstance(imgs, list):
                            image_urls = [str(u) for u in imgs]
                        elif isinstance(imgs, str):
                            image_urls = [imgs]
                        else:
                            image_urls = []

                        item = Listing(
                            title=title,
                            price=price,
                            description=desc,
                            image_urls=image_urls,
                            location=None,
                            timestamp=datetime.now(timezone.utc),
                        )
                        yield item

        # DBA pagination exposes <a rel="next" href="?page=2&q=...">
        next_page = (
            response.css('nav[aria-label="Pagination"] a[rel="next"]::attr(href)').get()
            or response.css('a[rel="next"]::attr(href)').get()
        )
        if next_page:
            yield response.follow(next_page, callback=self.parse)


def fetch_dynamic(url: str, wait_time: float = 0.0) -> str:
    """Fetch page HTML using Selenium for sites requiring JS rendering."""

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
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
