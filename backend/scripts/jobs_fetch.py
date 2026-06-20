"""Pull job postings via JobSpy from the CLI (pre-fetch / test the source).

  python scripts/jobs_fetch.py "software engineer intern" --location "San Francisco, CA"
  python scripts/jobs_fetch.py "data analyst" --out app/data/jobs.json

Indeed has no rate limiting; LinkedIn does (add --sites linkedin only with proxies).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.jobs import DEFAULT_SITES, fetch_jobs  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull job postings via JobSpy.")
    parser.add_argument("target")
    parser.add_argument("--location", default="United States")
    parser.add_argument("--sites", default=",".join(DEFAULT_SITES))
    parser.add_argument("--results", type=int, default=15)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    jobs = asyncio.run(
        fetch_jobs(
            args.target,
            location=args.location,
            sites=args.sites.split(","),
            results=args.results,
        )
    )
    print(f"Found {len(jobs)} jobs")
    for job in jobs[:5]:
        print(f"  - {job['title']} | {job['company']} | {job['location']} [{job['site']}]")
    if args.out:
        Path(args.out).write_text(json.dumps(jobs, indent=2), encoding="utf-8")
        print(f"-> wrote {len(jobs)} jobs to {args.out}")


if __name__ == "__main__":
    main()
