from __future__ import annotations

from scrapy.http import HtmlResponse

from dba_agent.services import ListingSpider
from dba_agent.models import Listing
import dba_agent.services.scraper as scraper
import pytest


HTML = """
<html>
  <body>
    <div class="listing">
      <h2>Widget</h2>
      <span class="price">$9.99</span>
      <p class="description">Great widget</p>
      <img src="http://example.com/img1.jpg" />
      <span class="location">Springfield</span>
    </div>
    <a class="next" href="/page2.html">Next</a>
  </body>
</html>
"""


def test_listing_spider_parses_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download(url: str) -> bytes | None:
        return b"imgbytes"

    monkeypatch.setattr(scraper, "download_image", fake_download)

    spider = ListingSpider(start_urls=["http://example.com"])
    response = HtmlResponse(url="http://example.com", body=HTML, encoding="utf-8")
    results = list(spider.parse(response))

    assert results
    listing = results[0]
    assert isinstance(listing, Listing)
    assert listing.title == "Widget"
    assert listing.price == 9.99
    assert listing.images == [b"imgbytes"]
    assert listing.location == "Springfield"
