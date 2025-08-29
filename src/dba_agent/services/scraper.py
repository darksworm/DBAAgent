"""Web scraping utilities built on Scrapy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional

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
    }

    def __init__(
        self, start_urls: Optional[Iterable[str]] = None, **kwargs: object
    ) -> None:
        super().__init__(**kwargs)
        self.start_urls = list(start_urls or [])

    def parse(
        self, response: Response, **kwargs: object
    ) -> Iterator[Listing | Request]:
        """Parse listing cards on the page and follow pagination links."""

        for card in response.css("div.listing"):
            yield Listing(
                title=card.css("h2::text").get(default="").strip(),
                price=float(card.css("span.price::text").re_first(r"[\d.]+") or 0.0),
                description=card.css("p.description::text").get(),
                image_urls=card.css("img::attr(src)").getall(),
                location=card.css("span.location::text").get(),
                timestamp=datetime.now(timezone.utc),
            )

        next_page = response.css("a.next::attr(href)").get()
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
