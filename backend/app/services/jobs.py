"""Pull real job postings via JobSpy and normalize to JSON; store in Redis.

Replaces the pysimular/Sai LinkedIn-scrape approach: JobSpy is a pure-Python library
(no GUI app) that scrapes Indeed / Google / ZipRecruiter / LinkedIn and returns a
DataFrame. Indeed has no rate limiting (LinkedIn does), so we default to the reliable
boards. Pulled jobs are stored in Redis (the per-target store) so the report/benchmark
can read them later — this is the "pull + remember" system; it is NOT wired into
scoring yet.

Optional dependency: ``pip install -r requirements-jobs.txt``. Lazily imported so the
core backend stays installable without it.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Optional

from app.services.store import get_store

logger = logging.getLogger("hired.jobs")

# Reliable boards by default (LinkedIn rate-limits without proxies).
DEFAULT_SITES = ["indeed", "google", "zip_recruiter"]
_MAX_DESC = 3000


def _s(value) -> str:
    """Safe string: turn None / pandas NaN into ''."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def normalize(df) -> list[dict]:
    """Turn a JobSpy DataFrame into a list of plain job dicts (robust to columns)."""
    records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    jobs: list[dict] = []
    for raw in records:
        row = {str(k).lower(): v for k, v in raw.items()}
        city, state = _s(row.get("city")), _s(row.get("state"))
        location = _s(row.get("location")) or ", ".join(p for p in (city, state) if p)
        if not location and row.get("is_remote"):
            location = "Remote"
        jobs.append(
            {
                "title": _s(row.get("title")),
                "company": _s(row.get("company")),
                "location": location,
                "url": _s(row.get("job_url")) or _s(row.get("url")),
                "site": _s(row.get("site")),
                "description": _s(row.get("description"))[:_MAX_DESC],
            }
        )
    return [j for j in jobs if j["title"] and j["company"]]


async def fetch_jobs(
    target: str,
    *,
    location: str = "United States",
    sites: Optional[list[str]] = None,
    results: int = 15,
    hours_old: int = 168,
) -> list[dict]:
    """Scrape jobs for `target` and return normalized dicts (empty on failure)."""
    sites = sites or DEFAULT_SITES

    def _scrape() -> list[dict]:
        from jobspy import scrape_jobs  # lazy: optional dep

        df = scrape_jobs(
            site_name=sites,
            search_term=target,
            google_search_term=f"{target} jobs near {location}",
            location=location,
            results_wanted=results,
            hours_old=hours_old,
            country_indeed="USA",
        )
        return normalize(df)

    try:
        return await asyncio.to_thread(_scrape)
    except Exception as exc:  # import error, network block, 429, etc.
        logger.warning("JobSpy fetch failed for %r: %s", target, exc)
        return []


def jobs_key(target: str) -> str:
    return f"jobs:{target.strip().lower()}"


async def fetch_and_store_jobs(target: str, **kwargs) -> list[dict]:
    """Pull jobs for `target` and remember them in Redis (best-effort)."""
    jobs = await fetch_jobs(target, **kwargs)
    if jobs:
        try:
            await get_store().set_json(jobs_key(target), jobs)
        except Exception:
            logger.exception("failed to store jobs for %r", target)
    return jobs


async def load_jobs(target: str) -> Optional[list[dict]]:
    return await get_store().get_json(jobs_key(target))
