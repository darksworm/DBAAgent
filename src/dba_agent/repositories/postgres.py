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
                  url TEXT,
                  image_urls JSONB,
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
                CREATE TABLE IF NOT EXISTS scrape_schedules (
                  id BIGSERIAL PRIMARY KEY,
                  name TEXT NOT NULL,
                  urls TEXT NOT NULL,
                  cadence_minutes INTEGER NOT NULL,
                  max_pages INTEGER,
                  workers INTEGER,
                  concurrency INTEGER,
                  newest_first BOOLEAN NOT NULL DEFAULT TRUE,
                  enabled BOOLEAN NOT NULL DEFAULT TRUE,
                  last_run TIMESTAMPTZ,
                  last_pub_ts TIMESTAMPTZ
                );
                """
            )
            # Backfill column if migrating
            cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS url TEXT;")
            cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS image_urls JSONB;")
            cur.execute("ALTER TABLE scrape_schedules ADD COLUMN IF NOT EXISTS last_pub_ts TIMESTAMPTZ;")
            cur.execute("ALTER TABLE scrape_schedules ADD COLUMN IF NOT EXISTS workers INTEGER;")
            cur.execute("ALTER TABLE scrape_schedules ADD COLUMN IF NOT EXISTS concurrency INTEGER;")
        conn.commit()


def listing_key(l: Listing) -> str:
    """Stable key for a listing used for upsert de-duplication.

    Prefer using the canonical URL if available; otherwise fall back to
    a composite of title/price/description prefix. Avoid using image bytes
    since images may be fetched asynchronously and would cause unstable keys.
    """
    url = getattr(l, "url", None) or ""
    if url:
        basis = url
    else:
        basis = f"{l.title}|{float(l.price)}|{(l.description or '')[:64]}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def upsert_many(items: Iterable[Listing]) -> int:
    # De-duplicate by key to avoid ON CONFLICT affecting the same row twice
    rows_by_key: Dict[str, Tuple[str, str, float, Optional[str], Optional[str], Optional[str], object, str]] = {}
    images_by_key: Dict[str, List[bytes]] = {}
    for l in items:
        k = listing_key(l)
        rows_by_key[k] = (
            k,
            l.title,
            float(l.price),
            l.description,
            l.location,
            getattr(l, "url", None),
            l.timestamp,
            json.dumps(getattr(l, "image_urls", []) or []),
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
                INSERT INTO listings (key, title, price, description, location, url, ts, image_urls)
                VALUES %s
                ON CONFLICT (key) DO UPDATE SET
                  title = EXCLUDED.title,
                  price = EXCLUDED.price,
                  description = EXCLUDED.description,
                  location = EXCLUDED.location,
                  url = EXCLUDED.url,
                  ts = EXCLUDED.ts,
                  image_urls = EXCLUDED.image_urls
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
        "SELECT l.id, l.title, l.price, l.description, l.location, l.url, l.ts, li.data as first_image, "
        "       COALESCE(jsonb_array_length(l.image_urls),0) as url_cnt, (l.image_urls ->> 0) as first_url "
        "FROM listings l "
        "LEFT JOIN LATERAL (SELECT data FROM listing_images WHERE listing_id=l.id ORDER BY idx ASC LIMIT 1) li ON TRUE "
        "LEFT JOIN LATERAL (SELECT COUNT(*) AS cnt FROM listing_images WHERE listing_id=l.id) ic ON TRUE "
        + where_sql.replace("WHERE ", "WHERE ")
        + (" AND COALESCE(jsonb_array_length(l.image_urls),0) >= %s" if min_images is not None else "")
        + " ORDER BY l.ts DESC LIMIT %s"
    )
    if min_images is not None:
        params.append(min_images)
    params.append(limit)
    results: List[Listing] = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for _id, title, price, desc, location, url, ts, first_image, _url_cnt, first_url in cur.fetchall():
                images_list: List[bytes] = [bytes(first_image)] if first_image is not None else []
                image_urls_list: List[str] = [first_url] if first_url else []
                results.append(
                    Listing(
                        title=title,
                        price=float(price),
                        description=desc,
                        images=images_list,
                        image_urls=image_urls_list,
                        location=location,
                        url=url,
                        timestamp=ts,
                    )
                )
    return results


def recent_listings(since: Optional[datetime] = None, limit: int = 20) -> List[Listing]:
    where = []
    params: List[object] = []
    if since is not None:
        where.append("l.ts > %s")
        params.append(since)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT l.id, l.title, l.price, l.description, l.location, l.url, l.ts, li.data as first_image, COALESCE(jsonb_array_length(l.image_urls),0) as url_cnt "
        "FROM listings l "
        "LEFT JOIN LATERAL (SELECT data FROM listing_images WHERE listing_id=l.id ORDER BY idx ASC LIMIT 1) li ON TRUE "
        + where_sql
        + " ORDER BY l.ts DESC LIMIT %s"
    )
    params.append(limit)
    results: List[Listing] = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for _id, title, price, desc, location, url, ts, first_image, _url_cnt in cur.fetchall():
                images_list: List[bytes] = [bytes(first_image)] if first_image is not None else []
                results.append(
                    Listing(
                        title=title,
                        price=float(price),
                        description=desc,
                        images=images_list,
                        location=location,
                        url=url,
                        timestamp=ts,
                    )
                )
    return results


# Scheduling helpers
def schedule_create(
    name: str,
    urls: str,
    cadence_minutes: int,
    max_pages: Optional[int],
    newest_first: bool,
    workers: Optional[int] = None,
    concurrency: Optional[int] = None,
) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scrape_schedules (name, urls, cadence_minutes, max_pages, workers, concurrency, newest_first, enabled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
                RETURNING id
                """,
                (name, urls, cadence_minutes, max_pages, workers, concurrency, newest_first),
            )
            sid = cur.fetchone()[0]
        conn.commit()
        return int(sid)


def schedule_list() -> List[dict]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, urls, cadence_minutes, max_pages, workers, concurrency, newest_first, enabled, last_run, last_pub_ts FROM scrape_schedules ORDER BY id DESC"
            )
            rows = cur.fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "name": r[1],
                "urls": r[2],
                "cadence_minutes": r[3],
                "max_pages": r[4],
                "workers": r[5],
                "concurrency": r[6],
                "newest_first": bool(r[7]),
                "enabled": bool(r[8]),
                "last_run": r[9],
                "last_pub_ts": r[10],
            }
        )
    return out


def schedule_toggle(sid: int, enabled: bool) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scrape_schedules SET enabled=%s WHERE id=%s",
                (enabled, sid),
            )
        conn.commit()


def schedule_mark_ran(sid: int, when: Optional[datetime] = None) -> None:
    when = when or datetime.now(timezone.utc)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scrape_schedules SET last_run=%s WHERE id=%s",
                (when, sid),
            )
        conn.commit()


def schedules_due(now: Optional[datetime] = None) -> List[dict]:
    now = now or datetime.now(timezone.utc)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, urls, cadence_minutes, max_pages, workers, concurrency, newest_first, enabled, last_run, last_pub_ts
                FROM scrape_schedules
                WHERE enabled = TRUE
                  AND (last_run IS NULL OR last_run <= %s - (cadence_minutes || ' minutes')::interval)
                """,
                (now,),
            )
            rows = cur.fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "name": r[1],
                "urls": r[2],
                "cadence_minutes": r[3],
                "max_pages": r[4],
                "workers": r[5],
                "concurrency": r[6],
                "newest_first": bool(r[7]),
                "enabled": bool(r[8]),
                "last_run": r[9],
                "last_pub_ts": r[10],
            }
        )
    return out


def schedule_mark_pub(sid: int, ts: datetime) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scrape_schedules SET last_pub_ts = GREATEST(COALESCE(last_pub_ts, '-infinity'), %s) WHERE id=%s",
                (ts, sid),
            )
        conn.commit()


def schedule_delete(sid: int) -> None:
    """Delete a schedule by id."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scrape_schedules WHERE id=%s", (sid,))
        conn.commit()
