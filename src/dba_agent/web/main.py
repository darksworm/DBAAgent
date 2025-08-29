from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import os

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dba_agent.models import Listing
from dba_agent.filters import FilterConfig, FilterEngine
from dba_agent.repositories import __init__ as repo_init  # type: ignore
from dba_agent.repositories.postgres import init_schema, search as db_search, upsert_many


app = FastAPI(title="DBA Deal-Finding")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


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
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    min_images: Optional[int] = Query(None),
    max_age_days: Optional[int] = Query(None),
) -> HTMLResponse:
    include = (q or "").split()
    exclude = (qx or "").split()
    loc_inc = (loc or "").split()
    loc_exc = (locx or "").split()
    cfg = FilterConfig(
        min_price=min_price,
        max_price=max_price,
        include_keywords=include,
        exclude_keywords=exclude,
        location_includes=loc_inc,
        location_excludes=loc_exc,
        min_images=min_images,
        max_age_days=max_age_days,
    )
    engine = FilterEngine(cfg)
    listings: List[Listing]
    try:
        listings = db_search(
            include_keywords=include,
            exclude_keywords=exclude,
            location_includes=loc_inc,
            location_excludes=loc_exc,
            min_images=min_images,
            max_age_days=max_age_days,
            min_price=min_price,
            max_price=max_price,
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
    # Compute score and filter using engine
    scored = []
    for l in listings:
        fr = engine.apply(l)
        if fr.included:
            scored.append({"item": l, "score": fr.score})
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
