from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from dba_agent.models import Listing
from dba_agent.repositories.postgres import upsert_many
from .events import hub
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse


def _append_query(url: str, extra: dict[str, str]) -> str:
    try:
        u = urlparse(url)
        q = dict(parse_qsl(u.query))
        q.update(extra)
        return urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(q), u.fragment))
    except Exception:
        return url


@dataclass
class ScrapeJob:
    id: str
    start_urls: str
    outfile: Path
    status: str = "starting"  # starting|running|stopping|completed|failed|canceled
    inserted: int = 0
    errors: int = 0
    last_error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    _proc: Optional[subprocess.Popen] = None
    _thread: Optional[threading.Thread] = None


class JobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, ScrapeJob] = {}
        self._lock = threading.Lock()

    def start(
        self,
        start_urls: str,
        max_pages: Optional[int] = None,
        newest_first: bool = False,
        stop_before_ts: Optional[str] = None,
        settings: Optional[dict[str, object]] = None,
    ) -> ScrapeJob:
        job_id = uuid.uuid4().hex[:8]
        outfile = Path.cwd() / f"scrape-{job_id}.jl"
        if newest_first:
            parts = [p for p in start_urls.replace(',', ' ').split() if p]
            parts = [_append_query(p, {"sort": "PUBLISHED_DESC"}) for p in parts]
            start_urls = " ".join(parts)
        job = ScrapeJob(id=job_id, start_urls=start_urls, outfile=outfile)
        with self._lock:
            self._jobs[job_id] = job
        # Build subprocess command (JSON Lines output for incremental ingest)
        spider_path = Path(__file__).resolve().parents[1] / "services" / "scraper.py"
        cmd = [
            "scrapy",
            "runspider",
            str(spider_path),
            "-a",
            f"start_urls={start_urls}",
        ]
        if max_pages is not None:
            cmd += [
                "-a",
                f"max_pages={int(max_pages)}",
            ]
        if stop_before_ts:
            cmd += [
                "-a",
                f"stop_before_ts={stop_before_ts}",
            ]
        # Extra Scrapy settings from caller
        if settings:
            for k, v in settings.items():
                cmd += ["-s", f"{k}={v}"]
        cmd += [
            "-o",
            str(outfile),
        ]
        # Start process
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path.cwd()),
            env=os.environ.copy(),
        )
        job._proc = proc
        job.status = "running"
        # Start reader thread
        t = threading.Thread(target=self._reader_loop, args=(job,), daemon=True)
        job._thread = t
        t.start()
        return job

    def _reader_loop(self, job: ScrapeJob) -> None:
        buffer: List[Listing] = []
        batch_size = 20
        outfile = job.outfile
        # Wait for file to appear
        for _ in range(300):  # up to ~30s
            if outfile.exists():
                break
            if job._proc and job._proc.poll() is not None:
                # Process exited before writing
                break
            time.sleep(0.1)
        try:
            f = None
            if outfile.exists():
                f = outfile.open("r", encoding="utf-8")
            last_flush = time.time()
            # Read lines as they are written
            while True:
                # If process ended and no file, break
                if (job._proc and job._proc.poll() is not None) and not f:
                    break
                line = None
                if f:
                    line = f.readline()
                if line:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        imgs = obj.get("images")
                        if isinstance(imgs, list) and imgs and isinstance(imgs[0], str):
                            obj = dict(obj)
                            obj["images"] = [base64.b64decode(s) for s in imgs]
                        buffer.append(Listing(**obj))
                    except Exception as e:  # malformed/partial JSON or validation error
                        job.errors += 1
                        job.last_error = str(e)
                    # Flush batch on size
                    if len(buffer) >= batch_size:
                        self._flush(job, buffer)
                        buffer.clear()
                        last_flush = time.time()
                else:
                    # Nothing new; consider flushing on time
                    if buffer and (time.time() - last_flush) > 1.5:
                        self._flush(job, buffer)
                        buffer.clear()
                        last_flush = time.time()
                    # If process finished and file reached EOF, stop
                    if job._proc and job._proc.poll() is not None:
                        break
                    time.sleep(0.25)
        finally:
            # Final flush
            if buffer:
                self._flush(job, buffer)
            job.finished_at = time.time()
            # Determine final status
            code = job._proc.returncode if job._proc else 0
            if job.status == "stopping":
                job.status = "canceled"
            elif code == 0 and job.errors == 0:
                job.status = "completed"
            elif code == 0:
                job.status = "completed"
            else:
                job.status = "failed"

    def _flush(self, job: ScrapeJob, items: List[Listing]) -> None:
        try:
            n = upsert_many(items)
            job.inserted += n
            # Notify listeners that new results are available
            hub.publish("new_results")
        except Exception as e:
            job.errors += 1
            job.last_error = str(e)

    def status(self, job_id: str) -> Optional[ScrapeJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def stop(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return False
        job.status = "stopping"
        if job._proc and job._proc.poll() is None:
            try:
                job._proc.terminate()
            except Exception:
                pass
        return True

    def list_recent(self, limit: int = 5) -> List[ScrapeJob]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.started_at, reverse=True)
        return jobs[:limit]
