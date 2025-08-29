from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class JsonifyPydantic:
    """Scrapy pipeline that converts Pydantic models to JSON-serializable dicts.

    - Calls ``model_dump(mode="json")`` on BaseModel instances so fields like
      ``HttpUrl`` and ``datetime`` serialize cleanly for feed exports.
    - Leaves plain dicts/items untouched.
    """

    def process_item(self, item: Any, spider: Any) -> Any:  # scrapy signature
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        return item

