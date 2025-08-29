from __future__ import annotations

from scrapy.logformatter import LogFormatter


class NoItemLogFormatter(LogFormatter):
    """Scrapy LogFormatter that omits the full item from 'scraped' logs.

    This prevents large fields (like base64-encoded images) from polluting the terminal
    while keeping normal logging intact.
    """

    def scraped(self, item, response, spider):  # type: ignore[override]
        data = super().scraped(item, response, spider)
        # Replace the default message and args to exclude the item body
        data["msg"] = "Scraped from %(src)s"
        data["args"] = {"src": response}
        return data

