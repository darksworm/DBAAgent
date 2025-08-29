from __future__ import annotations

from typing import Any

from pydantic import BaseModel
import base64


class JsonifyPydantic:
    """Scrapy pipeline that converts Pydantic models to JSON-serializable dicts.

    - Calls ``model_dump(mode="json")`` on BaseModel instances so fields like
      ``HttpUrl`` and ``datetime`` serialize cleanly for feed exports.
    - Leaves plain dicts/items untouched.
    """

    def process_item(self, item: Any, spider: Any) -> Any:  # scrapy signature
        if isinstance(item, BaseModel):
            data = item.model_dump(mode="python")
            imgs = data.get("images") if isinstance(data, dict) else None
            if isinstance(imgs, list):
                out = []
                for b in imgs:
                    if isinstance(b, (bytes, bytearray)):
                        out.append(base64.b64encode(b).decode("ascii"))
                    else:
                        out.append(b)
                data["images"] = out
            return data
        return item
