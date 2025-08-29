from __future__ import annotations

import json
import os
import hashlib
from contextlib import contextmanager
from typing import Iterable, List, Optional, Sequence, Tuple
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

from dba_agent.models import Listing


def db_url() -> str:
    return os.environ.get("DB_URL", "postgresql://dba:dba@db:5432/dba")


@contextmanager
def connect():
    conn = psycopg2.connect(db_url())
    try:
        yield conn
    finally:
        conn.close()


def init_schema() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS listings (
                  id BIGSERIAL PRIMARY KEY,
                  key TEXT UNIQUE,
                  title TEXT NOT NULL,
                  price DOUBLE PRECISION NOT NULL,
                  description TEXT,
                  image_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
                  location TEXT,
                  ts TIMESTAMPTZ NOT NULL
                );
                CREATE INDEX IF NOT EXISTS listings_price_idx ON listings(price);
                CREATE INDEX IF NOT EXISTS listings_ts_idx ON listings(ts);
                """
            )
        conn.commit()


def listing_key(l: Listing) -> str:
    first_img = str(l.image_urls[0]) if l.image_urls else ""
    basis = f"{l.title}|{l.price}|{(l.description or '')[:64]}|{first_img}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def upsert_many(items: Iterable[Listing]) -> int:
    rows = []
    for l in items:
        rows.append(
            (
                listing_key(l),
                l.title,
                float(l.price),
                l.description,
                json.dumps([str(u) for u in l.image_urls]),
                l.location,
                l.timestamp,
            )
        )
    if not rows:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO listings (key, title, price, description, image_urls, location, ts)
                VALUES %s
                ON CONFLICT (key) DO UPDATE SET
                  title = EXCLUDED.title,
                  price = EXCLUDED.price,
                  description = EXCLUDED.description,
                  image_urls = EXCLUDED.image_urls,
                  location = EXCLUDED.location,
                  ts = EXCLUDED.ts
                """,
                rows,
                page_size=200,
            )
        conn.commit()
        return len(rows)


def search(
    include_keywords: Sequence[str] | None = None,
    exclude_keywords: Sequence[str] | None = None,
    location_includes: Sequence[str] | None = None,
    location_excludes: Sequence[str] | None = None,
    min_images: Optional[int] = None,
    max_age_days: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    limit: int = 100,
) -> List[Listing]:
    where = []
    params: List[object] = []
    if min_price is not None:
        where.append("price >= %s")
        params.append(min_price)
    if max_price is not None:
        where.append("price <= %s")
        params.append(max_price)
    if include_keywords:
        for kw in include_keywords:
            if kw:
                where.append("(LOWER(title) LIKE %s OR LOWER(description) LIKE %s)")
                like = f"%{kw.lower()}%"
                params.extend([like, like])
    if exclude_keywords:
        for kw in exclude_keywords:
            if kw:
                where.append("NOT (LOWER(title) LIKE %s OR LOWER(description) LIKE %s)")
                like = f"%{kw.lower()}%"
                params.extend([like, like])
    if location_includes:
        for kw in location_includes:
            if kw:
                where.append("LOWER(location) LIKE %s")
                params.append(f"%{kw.lower()}%")
    if location_excludes:
        for kw in location_excludes:
            if kw:
                where.append("NOT (LOWER(location) LIKE %s)")
                params.append(f"%{kw.lower()}%")
    if min_images is not None:
        where.append("jsonb_array_length(image_urls) >= %s")
        params.append(min_images)
    if max_age_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        where.append("ts >= %s")
        params.append(cutoff)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT title, price, description, image_urls, location, ts FROM listings"
        + where_sql
        + " ORDER BY ts DESC LIMIT %s"
    )
    params.append(limit)
    results: List[Listing] = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for title, price, desc, image_urls, location, ts in cur.fetchall():
                try:
                    images = json.loads(image_urls) if isinstance(image_urls, str) else image_urls
                except Exception:
                    images = []
                results.append(
                    Listing(
                        title=title,
                        price=float(price),
                        description=desc,
                        image_urls=images or [],
                        location=location,
                        timestamp=ts,
                    )
                )
    return results
