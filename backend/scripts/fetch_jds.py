"""Fetch job descriptions via JobSpy (python-jobspy) and write to a JSON file.

Replaces the Sai/simulang-based fetch_jds.ts. No browser automation required —
JobSpy scrapes LinkedIn, Indeed, Glassdoor, and ZipRecruiter directly.

SETUP:
  pip install python-jobspy

USAGE:
  python scripts/fetch_jds.py "ML Engineer" --location "San Francisco, CA"
  python scripts/fetch_jds.py "SWE Intern" --sites linkedin indeed --count 15
  python scripts/fetch_jds.py "Data Scientist" --out app/data/jds_live.json

OUTPUT: app/data/jds_live.json (set JD_DATA_PATH= in backend/.env)
  {"jds": [{"title", "company", "location", "salary", "url", "description"}]}
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs

_INTERVAL_ABBR = {"yearly": "yr", "monthly": "mo", "weekly": "wk", "hourly": "hr"}
_VALID_SITES = ["linkedin", "indeed", "glassdoor", "zip_recruiter", "google"]


def _format_salary(row: pd.Series) -> str:
    """Format min/max salary amounts into a human-readable string."""
    lo = row.get("min_amount")
    hi = row.get("max_amount")
    currency = str(row.get("currency") or "USD")
    interval = str(row.get("interval") or "yearly")
    abbr = _INTERVAL_ABBR.get(interval, interval)

    # Treat NaN / None as absent
    lo_ok = lo is not None and not (isinstance(lo, float) and math.isnan(lo))
    hi_ok = hi is not None and not (isinstance(hi, float) and math.isnan(hi))

    if not lo_ok and not hi_ok:
        return ""

    def fmt(amount: float) -> str:
        if currency == "USD":
            return f"${amount:,.0f}"
        return f"{currency} {amount:,.0f}"

    if lo_ok and hi_ok:
        if currency == "USD":
            return f"${lo:,.0f}–${hi:,.0f}/{abbr}"
        return f"{currency} {lo:,.0f}–{hi:,.0f}/{abbr}"
    if lo_ok:
        return f"{fmt(lo)}+/{abbr}"
    return f"up to {fmt(hi)}/{abbr}"


def _str(val: object) -> str:
    """Convert a value to string, coercing NaN/None to ''."""
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    return str(val).strip()


def _row_to_jd(row: pd.Series) -> dict:
    return {
        "title": _str(row.get("title")),
        "company": _str(row.get("company")),
        "location": _str(row.get("location")),
        "salary": _format_salary(row),
        "url": _str(row.get("job_url")),
        "description": _str(row.get("description")),
    }


def fetch(
    search_term: str,
    *,
    location: str = "United States",
    sites: list[str] | None = None,
    results_wanted: int = 10,
    hours_old: int = 72,
) -> list[dict]:
    """Scrape jobs and return a list of JD dicts ready to write to JSON."""
    if sites is None:
        sites = ["linkedin", "indeed"]

    df: pd.DataFrame = scrape_jobs(
        site_name=sites,
        search_term=search_term,
        location=location,
        results_wanted=results_wanted,
        hours_old=hours_old,
        linkedin_fetch_description=True,
        country_indeed="USA",
    )

    jds = []
    for _, row in df.iterrows():
        jd = _row_to_jd(row)
        if jd["title"] and jd["description"]:
            jds.append(jd)
    return jds


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Fetch job descriptions via JobSpy and write JSON for JD_DATA_PATH."
    )
    parser.add_argument("search_term", help='Role to search, e.g. "ML Engineer Intern"')
    parser.add_argument("--location", default="United States", help="Location filter")
    parser.add_argument(
        "--sites",
        nargs="+",
        default=["linkedin", "indeed"],
        choices=_VALID_SITES,
        metavar="SITE",
        help=f"Job sites to scrape (default: linkedin indeed). Choices: {', '.join(_VALID_SITES)}",
    )
    parser.add_argument("--count", type=int, default=10, help="Max results per site")
    parser.add_argument("--hours-old", type=int, default=72, help="Max listing age in hours")
    parser.add_argument(
        "--out",
        default="app/data/jds_live.json",
        help="Output JSON path (default: app/data/jds_live.json)",
    )
    args = parser.parse_args(argv)

    print(f'Fetching up to {args.count} JDs for: "{args.search_term}"')
    print(f"Sites: {', '.join(args.sites)} | Location: {args.location}")

    jds = fetch(
        args.search_term,
        location=args.location,
        sites=args.sites,
        results_wanted=args.count,
        hours_old=args.hours_old,
    )

    print(f"\nFetched {len(jds)} JDs:")
    for i, jd in enumerate(jds, 1):
        print(f'  [{i}] "{jd["title"]}" @ {jd["company"] or "?"} — {jd["location"] or "?"}')

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"jds": jds}, indent=2), encoding="utf-8")
    print(f"\nWrote {len(jds)} JDs → {out}")
    print(f"Set JD_DATA_PATH={out} in backend/.env")


if __name__ == "__main__":
    main()
