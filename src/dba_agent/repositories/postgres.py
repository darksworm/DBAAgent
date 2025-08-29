from __future__ import annotations

import json
import os
import hashlib
from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
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
                  location TEXT,
                  ts TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS listing_images (
                  listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
                  idx INTEGER NOT NULL,
                  data BYTEA NOT NULL,
                  PRIMARY KEY (listing_id, idx)
                );
                CREATE INDEX IF NOT EXISTS listings_price_idx ON listings(price);
                CREATE INDEX IF NOT EXISTS listings_ts_idx ON listings(ts);
                CREATE INDEX IF NOT EXISTS listing_images_listing_idx ON listing_images(listing_id);
                """
            )
        conn.commit()


def listing_key(l: Listing) -> str:
    first_img = l.images[0] if getattr(l, "images", None) else b""
    img_sig = hashlib.sha1(first_img).hexdigest() if first_img else ""
    basis = f"{l.title}|{l.price}|{(l.description or '')[:64]}|{img_sig}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def upsert_many(items: Iterable[Listing]) -> int:
    # De-duplicate by key to avoid ON CONFLICT affecting the same row twice
    rows_by_key: Dict[str, Tuple[str, str, float, Optional[str], Optional[str], object]] = {}
    images_by_key: Dict[str, List[bytes]] = {}
    for l in items:
        k = listing_key(l)
        rows_by_key[k] = (
            k,
            l.title,
            float(l.price),
            l.description,
            l.location,
            l.timestamp,
        )
        images_by_key[k] = list(getattr(l, "images", []) or [])
    rows = list(rows_by_key.values())
    if not rows:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            # Upsert listings
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO listings (key, title, price, description, location, ts)
                VALUES %s
                ON CONFLICT (key) DO UPDATE SET
                  title = EXCLUDED.title,
                  price = EXCLUDED.price,
                  description = EXCLUDED.description,
                  location = EXCLUDED.location,
                  ts = EXCLUDED.ts
                """,
                rows,
                page_size=200,
            )
            # Fetch ids for keys
            keys = list(images_by_key.keys())
            cur.execute("SELECT id, key FROM listings WHERE key = ANY(%s)", (keys,))
            id_by_key = {k: i for i, k in cur.fetchall()}
            # Delete existing images for these listings
            if id_by_key:
                cur.execute(
                    "DELETE FROM listing_images WHERE listing_id = ANY(%s)",
                    (list(id_by_key.values()),),
                )
            # Insert images
            img_rows = []
            for k, imgs in images_by_key.items():
                lid = id_by_key.get(k)
                if not lid:
                    continue
                for idx, data in enumerate(imgs):
                    img_rows.append((lid, idx, psycopg2.Binary(data)))
            if img_rows:
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO listing_images (listing_id, idx, data) VALUES %s",
                    img_rows,
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
    # Image count handled via lateral join alias `ic` below
    if max_age_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        where.append("ts >= %s")
        params.append(cutoff)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT l.id, l.title, l.price, l.description, l.location, l.ts, li.data as first_image "
        "FROM listings l "
        "LEFT JOIN LATERAL (SELECT data FROM listing_images WHERE listing_id=l.id ORDER BY idx ASC LIMIT 1) li ON TRUE "
        "LEFT JOIN LATERAL (SELECT COUNT(*) AS cnt FROM listing_images WHERE listing_id=l.id) ic ON TRUE "
        + where_sql.replace("WHERE ", "WHERE ")
        + (" AND ic.cnt >= %s" if min_images is not None else "")
        + " ORDER BY l.ts DESC LIMIT %s"
    )
    if min_images is not None:
        params.append(min_images)
    params.append(limit)
    results: List[Listing] = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for _id, title, price, desc, location, ts, first_image in cur.fetchall():
                images_list: List[bytes] = [bytes(first_image)] if first_image is not None else []
                results.append(
                    Listing(
                        title=title,
                        price=float(price),
                        description=desc,
                        images=images_list,
                        location=location,
                        timestamp=ts,
                    )
                )
    return results
