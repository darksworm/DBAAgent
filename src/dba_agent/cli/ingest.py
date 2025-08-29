from __future__ import annotations

import argparse
import json
from pathlib import Path

from dba_agent.models import Listing
from dba_agent.repositories.postgres import init_schema, upsert_many


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest listings JSON into Postgres")
    parser.add_argument("file", type=Path, help="Path to listings.json")
    args = parser.parse_args()

    data = json.loads(args.file.read_text(encoding="utf-8"))
    items = []
    for obj in data or []:
        try:
            items.append(Listing(**obj))
        except Exception:
            continue
    init_schema()
    n = upsert_many(items)
    print(f"Inserted/updated {n} listings")


if __name__ == "__main__":
    main()

