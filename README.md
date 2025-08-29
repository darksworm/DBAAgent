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

4. **Run tests**

   ```bash
   docker compose run --rm app pytest
   ```

5. **Shutdown**

   ```bash
   docker compose down
   ```

The database and application run entirely inside containers so nothing needs to be installed on the host machine.
