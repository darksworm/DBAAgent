from __future__ import annotations

from scrapy.http import HtmlResponse

from dba_agent.services import ListingSpider
from dba_agent.models import Listing


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


def test_listing_spider_parses_listing() -> None:
    spider = ListingSpider(start_urls=["http://example.com"])
    response = HtmlResponse(url="http://example.com", body=HTML, encoding="utf-8")
    results = list(spider.parse(response))

    assert results
    listing = results[0]
    assert isinstance(listing, Listing)
    assert listing.title == "Widget"
    assert listing.price == 9.99
    assert [str(url) for url in listing.image_urls] == ["http://example.com/img1.jpg"]
    assert listing.location == "Springfield"
