# DBA Deal-Finding System

This repository contains the code for a modular scraper–filter–AI pipeline that identifies good deals from online listings.

See [TASK.md](TASK.md) for the detailed project plan and [ENGINEERING_GUIDELINES.md](ENGINEERING_GUIDELINES.md) for development standards.

## Web Scraper

The first deliverable is a Scrapy-based spider that extracts structured `Listing`
objects from listing pages.

Run the spider and save results to JSON:

```bash
scrapy runspider src/dba_agent/services/scraper.py -O listings.json
```

The output file contains newline-delimited JSON representations of each
`Listing` with fields for title, price, description, images, location and
timestamp.
