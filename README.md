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

   - Expose port 8000 is already configured in `docker-compose.yml`.
   - Start the app inside the container:

   ```bash
   docker compose exec app uvicorn dba_agent.web.main:app --host 0.0.0.0 --port 8000
   ```

   - Open http://localhost:8000 and use the form to filter.
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
