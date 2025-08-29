# DBA Deal-Finding System

This repository contains the code for a modular scraper–filter–AI pipeline that identifies good deals from online listings.

See [TASK.md](TASK.md) for the detailed project plan and [ENGINEERING_GUIDELINES.md](ENGINEERING_GUIDELINES.md) for development standards.

## Web Scraper

The first deliverable is a Scrapy-based spider that extracts structured `Listing`
objects from listing pages.

Run the spider and save results to JSON:

```bash
# Provide one or more URLs via -a start_urls (comma or space separated)
scrapy runspider src/dba_agent/services/scraper.py \
  -a start_urls="https://example.com/page1,https://example.com/page2" \
  -O listings.json
```

The output file contains newline-delimited JSON representations of each
`Listing` with fields for title, price, description, images, location and
timestamp.

## Start Scraping From The Web UI

You can trigger a scrape directly from the UI and watch progress live. The app
streams updates via SSE and batches DB inserts so results appear quickly.

1. Start the stack and web app (see Docker instructions below), then open http://localhost:8000
2. Enter one or more start URLs and click "Start".
3. The status panel shows inserted counts and errors; the results grid refreshes automatically as new items are ingested.

## Running Locally with Docker

The repository includes a Docker setup for local development. It provides a Postgres database and an application container with all Python dependencies.

1. **Build images**

   ```bash
   docker compose build
   ```

2. **Start the database**

   ```bash
   docker compose up -d db
   ```

3. **Run the scraper**

```bash
docker compose run --rm app \
  scrapy runspider src/dba_agent/services/scraper.py \
 -a start_urls="https://example.com/page1 https://example.com/page2" \
  -O listings.json
```

4. **Web UI (FastAPI + HTMX)**

   The UI reads from Postgres (fallback to `listings.json` if DB is unavailable).

   - The app now starts automatically with `docker compose up -d` and listens on port 8000.
   - Open http://localhost:8000 and use the form to filter (and start scrapes).
   - Optionally ingest the latest `listings.json` into Postgres:

   ```bash
   curl -X POST http://localhost:8000/ingest
   ```

5. **Run tests**

   ```bash
   docker compose run --rm app pytest
   ```

6. **Shutdown**

   ```bash
   docker compose down
   ```

The database and application run entirely inside containers so nothing needs to be installed on the host machine.


## Watch Valuation (Chrono24)

The app exposes an Estimated Resale Price service for watches using Chrono24's
completed listings.

- Endpoint: `POST /api/watch/value`
  - Body: `{ "title": "Seiko SKX007K2", "price_dkk": 1200, "condition": "used" }`
  - Returns:
    ```json
    {
      "model": "SKX007",
      "estimated_resale_dkk": 1500,
      "listed_price_dkk": 1200,
      "deal_score": 0.2,
      "tag": "Exceptional"
    }
    ```

### Configuration

- `CHRONO24_CACHE_TTL_SECS`: Cache TTL (seconds) for sold price results (default 43200 = 12h).
- `REDIS_URL`: Optional Redis URL for caching. Without it, an in-process cache is used.
- `FX_EUR_TO_DKK`: EUR→DKK FX rate used to convert Chrono24 EUR prices (default 7.45).
- `WATCH_RIDGE_MODEL`: Path to an optional scikit-learn Ridge model (`.pkl`). If missing, the service
  falls back to median-of-sold-prices or returns an unavailable error if insufficient data.

Implementation uses the community `chrono24` library to retrieve completed listings; ensure the
package is installed (it is listed in `pyproject.toml`). If the library requires a browser runtime,
run it in a worker container with the necessary system dependencies.

### Implementation Notes

- Chrono24 client respects a minimal client-side interval between requests and caches responses
  for 12 hours via Redis (if configured).
- Model normalization strips punctuation/case and maps aliases (e.g., `SKX007K2` → `SKX007`).
- Estimation uses the median of sold prices (last 90 days, EUR), converted to DKK; if fewer than 5
  data points, a Ridge regressor can be used as a fallback.


