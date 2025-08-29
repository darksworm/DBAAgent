from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import os

from fastapi import FastAPI, Query, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from dba_agent.models import Listing
from dba_agent.filters import FilterConfig, FilterEngine
from dba_agent.repositories import __init__ as repo_init  # type: ignore
from dba_agent.repositories.postgres import (
    init_schema,
    search as db_search,
    upsert_many,
    schedule_create,
    schedule_list,
    schedule_toggle,
    schedule_mark_ran,
    schedules_due,
    recent_listings,
    schedule_delete,
)
from .jobs import JobManager
from .events import hub
import asyncio
import queue
from dba_agent.services.classifier import get_classifier


app = FastAPI(title="DBA Deal-Finding")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
jobs = JobManager()


def load_sample_listings() -> List[Listing]:
    # Load from a JSON file created by the spider if it exists
    p = Path.cwd() / "listings.json"
    if not p.exists():
        return []
    try:
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        items = []
        for obj in data or []:
            try:
                imgs = obj.get("images")
                if isinstance(imgs, list) and imgs and isinstance(imgs[0], str):
                    # Likely base64-encoded; decode
                    import base64

                    obj = dict(obj)
                    obj["images"] = [base64.b64decode(s) for s in imgs]
                items.append(Listing(**obj))
            except Exception:
                continue
        return items
    except Exception:
        return []


@app.on_event("startup")
def on_startup() -> None:
    try:
        init_schema()
    except Exception:
        # DB may not be up; UI still works with file fallback
        pass
    # Start background scheduler (best-effort)
    try:
        async def scheduler_loop() -> None:
            while True:
                try:
                    due = schedules_due()
                    for s in due:
                        cutoff = s["last_pub_ts"].isoformat() if s.get("last_pub_ts") else None
                        if jobs.is_schedule_running(int(s["id"])):
                            continue
                        extra_settings: dict[str, object] = {}
                        if s.get("concurrency"):
                            c = int(s["concurrency"]) or 0
                            if c > 0:
                                extra_settings.update({
                                    "CONCURRENT_REQUESTS": c,
                                    "CONCURRENT_REQUESTS_PER_DOMAIN": c,
                                    "AUTOTHROTTLE_ENABLED": False,
                                    "DOWNLOAD_DELAY": 0,
                                })
                        urls = [u for u in str(s.get("urls") or "").replace(",", " ").split() if u]
                        w = int(s.get("workers") or 0)
                        if w and w > 1 and len(urls) > 1:
                            n = max(1, min(w, len(urls)))
                            size = (len(urls) + n - 1) // n
                            shards = [" ".join(urls[i : i + size]) for i in range(0, len(urls), size)]
                        else:
                            shards = [" ".join(urls)] if urls else []
                        for shard in shards:
                            jobs.start(
                                shard,
                                max_pages=s.get("max_pages"),
                                newest_first=bool(s.get("newest_first", True)),
                                stop_before_ts=cutoff,
                                fetch_images=False,
                                schedule_id=int(s["id"]),
                                stop_on_known=False,
                                settings=extra_settings or None,
                            )
                        schedule_mark_ran(int(s["id"]))
                except Exception:
                    pass
                await asyncio.sleep(60)

        asyncio.get_event_loop().create_task(scheduler_loop())
    except Exception:
        pass


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    cfg = FilterConfig()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "config": cfg, "results": []},
    )


@app.get("/search", response_class=HTMLResponse)
def search(
    request: Request,
    q: Optional[str] = Query(None, description="Space-separated include keywords"),
    qx: Optional[str] = Query(None, description="Space-separated exclude keywords"),
    loc: Optional[str] = Query(None, description="Space-separated location include keywords"),
    locx: Optional[str] = Query(None, description="Space-separated location exclude keywords"),
    min_price: Optional[str] = Query(None),
    max_price: Optional[str] = Query(None),
    min_images: Optional[str] = Query(None),
    max_age_days: Optional[str] = Query(None),
    use_llm: Optional[bool] = Query(False),
) -> HTMLResponse:
    # Parse numeric inputs defensively to handle empty strings from forms
    def _f(s: Optional[str]) -> Optional[float]:
        try:
            return float(s) if s not in (None, "") else None
        except Exception:
            return None
    def _i(s: Optional[str]) -> Optional[int]:
        try:
            return int(s) if s not in (None, "") else None
        except Exception:
            return None
    min_price_v = _f(min_price)
    max_price_v = _f(max_price)
    min_images_v = _i(min_images)
    max_age_days_v = _i(max_age_days)
    include = (q or "").split()
    exclude = (qx or "").split()
    loc_inc = (loc or "").split()
    loc_exc = (locx or "").split()
    cfg = FilterConfig(
        min_price=min_price_v,
        max_price=max_price_v,
        include_keywords=include,
        exclude_keywords=exclude,
        location_includes=loc_inc,
        location_excludes=loc_exc,
        min_images=min_images_v,
        max_age_days=max_age_days_v,
    )
    engine = FilterEngine(cfg)
    listings: List[Listing]
    try:
        listings = db_search(
            include_keywords=include,
            exclude_keywords=exclude,
            location_includes=loc_inc,
            location_excludes=loc_exc,
            min_images=min_images_v,
            max_age_days=max_age_days_v,
            min_price=min_price_v,
            max_price=max_price_v,
            limit=100,
        )
    except Exception:
        # Fallback to local file if DB not reachable
        file_items = load_sample_listings()
        results = [l for l in file_items if engine.apply(l).included]
        return templates.TemplateResponse(
            "partials/results.html",
            {"request": request, "results": results, "config": cfg},
        )
    # Compute score and filter using engine. Since DB already enforced min_images,
    # avoid double-checking by disregarding min_images for the in-process filter.
    if cfg.min_images is not None:
        cfg.min_images = None
        engine = FilterEngine(cfg)

    import base64
    clf = get_classifier(include=include, exclude=exclude) if use_llm else None
    scored = []
    for l in listings:
        fr = engine.apply(l)
        if not fr.included:
            continue
        img_src = None
        if l.images:
            b64 = base64.b64encode(l.images[0]).decode("ascii")
            img_src = f"data:image/jpeg;base64,{b64}"
        elif getattr(l, "image_urls", None):
            try:
                first_url = l.image_urls[0]
                if isinstance(first_url, str) and first_url:
                    img_src = first_url
            except Exception:
                pass
        llm_score = None
        combined = fr.score
        if clf:
            text = f"{l.title}\n\n{l.description or ''}"
            try:
                llm_score = float(clf.score(text).score)
                combined = 0.5 * combined + 0.5 * llm_score
            except Exception:
                llm_score = None
                combined = fr.score
        scored.append({"item": l, "score": combined, "image_src": img_src, "llm": llm_score, "static": fr.score})
    return templates.TemplateResponse(
        "partials/results.html",
        {"request": request, "results": scored, "config": cfg},
    )


@app.post("/ingest", response_class=HTMLResponse)
def ingest_from_file(request: Request) -> HTMLResponse:
    items = load_sample_listings()
    try:
        inserted = upsert_many(items)
        msg = f"Ingested {inserted} listings into DB."
    except Exception as e:
        msg = f"DB ingest failed: {e}"
    return HTMLResponse(f"<pre>{msg}</pre>")


@app.post("/scrape", response_class=HTMLResponse)
def start_scrape(
    request: Request,
    start_urls: str = Form(...),
    newest_first: Optional[bool] = Form(False),
    pages: Optional[str] = Form(None),
    workers: Optional[str] = Form(None),
    concurrency: Optional[str] = Form(None)
) -> HTMLResponse:
    try:
        max_pages = int(pages) if pages else None
    except Exception:
        max_pages = None
    try:
        worker_count = int(workers) if workers else 1
    except Exception:
        worker_count = 1
    try:
        conc = int(concurrency) if concurrency else None
    except Exception:
        conc = None

    extra_settings = {}
    if conc and conc > 0:
        extra_settings.update({
            "CONCURRENT_REQUESTS": conc,
            "CONCURRENT_REQUESTS_PER_DOMAIN": conc,
            "AUTOTHROTTLE_ENABLED": False,
            "DOWNLOAD_DELAY": 0,
        })

    urls = [u for u in start_urls.replace(",", " ").split() if u]
    import uuid as _uuid
    group_id = _uuid.uuid4().hex[:6]
    if worker_count <= 1 or len(urls) <= 1:
        jobs.start(
            start_urls,
            max_pages=max_pages,
            newest_first=bool(newest_first),
            settings=extra_settings or None,
            group_id=group_id,
        )
    else:
        n = max(1, min(worker_count, len(urls)))
        size = (len(urls) + n - 1) // n
        shards = [" ".join(urls[i : i + size]) for i in range(0, len(urls), size)]
        for shard in shards:
            jobs.start(
                shard,
                max_pages=max_pages,
                newest_first=bool(newest_first),
                settings=extra_settings or None,
                group_id=group_id,
            )
    return templates.TemplateResponse(
        "partials/scrape_groups.html",
        {"request": request, "groups": jobs.list_groups()},
    )


@app.get("/scrape/status", response_class=HTMLResponse)
def scrape_status(request: Request, job_id: str) -> HTMLResponse:
    job = jobs.status(job_id)
    if not job:
        return HTMLResponse("<div>Unknown job.</div>", status_code=404)
    return templates.TemplateResponse(
        "partials/scrape_status.html",
        {"request": request, "job": job},
    )


@app.post("/scrape/stop")
def scrape_stop(job_id: str = Form(...)) -> JSONResponse:
    ok = jobs.stop(job_id)
    return JSONResponse({"ok": ok})


@app.get("/scrape/jobs", response_class=HTMLResponse)
def scrape_jobs(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "partials/scrape_groups.html",
        {"request": request, "groups": jobs.list_groups()},
    )


@app.post("/schedules", response_class=HTMLResponse)
def schedules_create_view(
    request: Request,
    name: str = Form(...),
    urls: str = Form(...),
    cadence_minutes: int = Form(1440),
    pages: Optional[str] = Form(None),
    workers: Optional[str] = Form(None),
    concurrency: Optional[str] = Form(None),
    newest_first: Optional[bool] = Form(True),
) -> HTMLResponse:
    max_pages = int(pages) if pages else None
    w = int(workers) if workers else None
    c = int(concurrency) if concurrency else None
    schedule_create(name=name, urls=urls, cadence_minutes=int(cadence_minutes), max_pages=max_pages, newest_first=bool(newest_first), workers=w, concurrency=c)
    return templates.TemplateResponse(
        "partials/schedules.html",
        {"request": request, "schedules": schedule_list()},
    )


@app.get("/schedules", response_class=HTMLResponse)
def schedules_view(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "partials/schedules.html",
        {"request": request, "schedules": schedule_list()},
    )


@app.post("/schedules/toggle", response_class=HTMLResponse)
def schedules_toggle_view(request: Request, sid: int = Form(...), enabled: bool = Form(...)) -> HTMLResponse:
    schedule_toggle(int(sid), bool(enabled))
    return templates.TemplateResponse(
        "partials/schedules.html",
        {"request": request, "schedules": schedule_list()},
    )


@app.post("/schedules/run", response_class=HTMLResponse)
def schedules_run_now(request: Request, sid: int = Form(...)) -> HTMLResponse:
    for s in schedule_list():
        if int(s["id"]) == int(sid):
            cutoff = s["last_pub_ts"].isoformat() if s.get("last_pub_ts") else None
            if jobs.is_schedule_running(int(sid)):
                return templates.TemplateResponse(
                    "partials/schedules.html",
                    {"request": request, "schedules": schedule_list()},
                )
            extra_settings: dict[str, object] = {}
            if s.get("concurrency"):
                c = int(s["concurrency"]) or 0
                if c > 0:
                    extra_settings.update({
                        "CONCURRENT_REQUESTS": c,
                        "CONCURRENT_REQUESTS_PER_DOMAIN": c,
                        "AUTOTHROTTLE_ENABLED": False,
                        "DOWNLOAD_DELAY": 0,
                    })
            urls = [u for u in str(s.get("urls") or "").replace(",", " ").split() if u]
            w = int(s.get("workers") or 0)
            if w and w > 1 and len(urls) > 1:
                n = max(1, min(w, len(urls)))
                size = (len(urls) + n - 1) // n
                shards = [" ".join(urls[i : i + size]) for i in range(0, len(urls), size)]
            else:
                shards = [" ".join(urls)] if urls else []
            for shard in shards:
                jobs.start(
                    shard,
                    max_pages=s.get("max_pages"),
                    newest_first=bool(s.get("newest_first", True)),
                    stop_before_ts=cutoff,
                    fetch_images=False,
                    schedule_id=int(s["id"]),
                    stop_on_known=False,
                    settings=extra_settings or None,
                )
            schedule_mark_ran(int(sid))
            break
    return templates.TemplateResponse(
        "partials/schedules.html",
        {"request": request, "schedules": schedule_list()},
    )


@app.get("/events")
async def sse_events() -> StreamingResponse:
    q: queue.Queue[bytes] = await hub.subscribe()

    async def event_stream():
        try:
            while True:
                payload = await asyncio.get_event_loop().run_in_executor(None, q.get)
                yield payload
        except asyncio.CancelledError:
            # Client disconnected
            pass
        finally:
            await hub.unsubscribe(q)

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
@app.get("/recent", response_class=HTMLResponse)
def recent(request: Request, since: Optional[str] = Query(None), limit: Optional[int] = Query(12)) -> HTMLResponse:
    from datetime import datetime
    since_dt: Optional[datetime] = None
    if since:
        try:
            s = since.rstrip("Z")
            since_dt = datetime.fromisoformat(s)
        except Exception:
            since_dt = None
    items = recent_listings(since=since_dt, limit=int(limit or 12))
    import base64
    cards = []
    latest_ts = since or ""
    for l in items:
        img_src = None
        if l.images:
            img_src = f"data:image/jpeg;base64,{base64.b64encode(l.images[0]).decode('ascii')}"
        ts_iso = l.timestamp.isoformat()
        if not latest_ts or ts_iso > latest_ts:
            latest_ts = ts_iso
        cards.append({"item": l, "image_src": img_src})
    return templates.TemplateResponse(
        "partials/recent.html",
        {"request": request, "cards": cards, "since": latest_ts},
    )


@app.post("/schedules/delete", response_class=__import__('fastapi').FastAPI.__annotations__.get('HTMLResponse', HTMLResponse))
def schedules_delete_view(request: Request, sid: int = Form(...)) -> HTMLResponse:
    # If a schedule is currently running, keep the job running but remove future runs
    schedule_delete(int(sid))
    return templates.TemplateResponse(
        "partials/schedules.html",
        {"request": request, "schedules": schedule_list()},
    )
