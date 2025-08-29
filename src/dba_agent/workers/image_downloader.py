from __future__ import annotations

import os
import time
from typing import List, Tuple
import requests
import psycopg2
import psycopg2.extras


DB_URL = os.environ.get("DB_URL", "postgresql://dba:dba@db:5432/dba")


def connect():
    return psycopg2.connect(DB_URL)


def find_listings_missing_images(limit: int = 50) -> List[Tuple[int, List[str]]]:
    sql = (
        "SELECT l.id, COALESCE(ARRAY(SELECT jsonb_array_elements_text(l.image_urls)), ARRAY[]::text[]) AS urls, "
        "COALESCE((SELECT COUNT(*) FROM listing_images WHERE listing_id=l.id), 0) AS have_cnt "
        "FROM listings l "
        "WHERE COALESCE(jsonb_array_length(l.image_urls),0) > COALESCE((SELECT COUNT(*) FROM listing_images WHERE listing_id=l.id),0) "
        "ORDER BY l.ts DESC LIMIT %s"
    )
    out: List[Tuple[int, List[str]]] = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            for lid, urls, _have in cur.fetchall():
                out.append((int(lid), list(urls)))
    return out


def download(url: str, timeout: float = 10.0) -> bytes | None:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return bytes(r.content)
    except Exception:
        return None


def store_images(listing_id: int, images: List[bytes]) -> None:
    rows = [(listing_id, idx, psycopg2.Binary(data)) for idx, data in enumerate(images)]
    if not rows:
        return
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM listing_images WHERE listing_id=%s", (listing_id,))
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO listing_images (listing_id, idx, data) VALUES %s",
                rows,
                page_size=200,
            )
        conn.commit()


def main_loop(interval: float = 2.0, batch_size: int = 25) -> None:
    while True:
        try:
            candidates = find_listings_missing_images(limit=batch_size)
            if not candidates:
                time.sleep(interval)
                continue
            for lid, urls in candidates:
                imgs: List[bytes] = []
                for u in urls:
                    if data := download(u):
                        imgs.append(data)
                if imgs:
                    store_images(lid, imgs)
        except Exception:
            time.sleep(interval)


if __name__ == "__main__":
    main_loop()

