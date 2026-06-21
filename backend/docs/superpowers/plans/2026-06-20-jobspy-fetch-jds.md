# JobSpy JD Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Sai/simulang-based TypeScript JD-fetch scripts with a single Python script (`scripts/fetch_jds.py`) backed by `python-jobspy`, producing the same `{"jds": [...]}` JSON file that `benchmark_agent.py` already consumes via `JD_DATA_PATH`.

**Architecture:** `scripts/fetch_jds.py` wraps JobSpy's `scrape_jobs()` — a headless, API-free multi-site scraper — and maps its DataFrame rows to the existing JD schema. Core mapping logic lives in importable helpers so tests don't need a real network call. The existing `app/config.py` (`JD_DATA_PATH`) and `agents/benchmark_agent.py` are unchanged.

**Tech Stack:** Python 3.12, `python-jobspy` (pip), `pandas` (pulled in by jobspy), `pytest`

## Global Constraints

- Output JSON schema **must** match what `benchmark_agent.py` reads: `{"jds": [{"title", "company", "location", "salary", "url", "description"}]}`
- Default output path: `app/data/jds_live.json` (relative to the `backend/` working directory)
- No changes to `app/config.py`, `agents/benchmark_agent.py`, or `app/services/sai_gateway.py`
- Python 3.12 (matches the repo's pinned runtime)
- `pytest` for tests; no mocking frameworks beyond `unittest.mock`
- Delete `scripts/fetch_jds.ts` and `scripts/debug_jd_cards.ts`; keep `scripts/sai_fetch.py`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Delete | `scripts/fetch_jds.ts` | Replaced by Python script |
| Delete | `scripts/debug_jd_cards.ts` | Replaced by Python script |
| Modify | `requirements.txt` | Add `python-jobspy` |
| Modify | `.env.example` | Fix comment on `JD_DATA_PATH` |
| **Create** | `scripts/fetch_jds.py` | CLI + mapping logic |
| **Create** | `tests/test_fetch_jds.py` | Unit tests for mapping helpers |

---

### Task 1: Delete TS scripts + add python-jobspy dependency

**Files:**
- Delete: `scripts/fetch_jds.ts`
- Delete: `scripts/debug_jd_cards.ts`
- Modify: `requirements.txt` (add one line after the `openai` entry)
- Modify: `.env.example` (fix `JD_DATA_PATH` comment)

**Interfaces:**
- Produces: `python-jobspy` available to import; TypeScript files gone

- [ ] **Step 1: Delete the TypeScript scripts**

```bash
rm backend/scripts/fetch_jds.ts
rm backend/scripts/debug_jd_cards.ts
```

- [ ] **Step 2: Add python-jobspy to requirements.txt**

In `requirements.txt`, after the line `openai>=1.57.0`, add:

```
python-jobspy>=2.3.4             # multi-site JD scraper (LinkedIn, Indeed, Glassdoor, ZipRecruiter)
```

- [ ] **Step 3: Update the JD_DATA_PATH comment in .env.example**

In `.env.example`, change line 44:
```
# Path to full JD text JSON produced by scripts/sai_fetch_jds.py (blank = no JD context)
```
to:
```
# Path to full JD text JSON produced by scripts/fetch_jds.py (blank = no JD context)
```

- [ ] **Step 4: Install the new dependency**

```bash
cd backend && pip install python-jobspy>=2.3.4
```

Expected: installs `python-jobspy` (and `pandas` if not already present) without errors.

- [ ] **Step 5: Verify import works**

```bash
cd backend && python -c "from jobspy import scrape_jobs; print('ok')"
```

Expected: prints `ok`

- [ ] **Step 6: Commit**

```bash
git rm backend/scripts/fetch_jds.ts backend/scripts/debug_jd_cards.ts
git add backend/requirements.txt backend/.env.example
git commit -m "chore: replace TS JD scripts with python-jobspy dependency"
```

---

### Task 2: Write tests for fetch_jds mapping helpers (TDD — tests first)

**Files:**
- Create: `tests/test_fetch_jds.py`

**Interfaces:**
- Consumes (from Task 3): `scripts.fetch_jds._format_salary(row: pd.Series) -> str`, `scripts.fetch_jds._row_to_jd(row: pd.Series) -> dict`
- Produces: failing test suite that will pass after Task 3

- [ ] **Step 1: Create tests/test_fetch_jds.py**

```python
"""Unit tests for scripts/fetch_jds.py mapping helpers."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_jds import _format_salary, _row_to_jd, fetch


# ── _format_salary ────────────────────────────────────────────────────────────

def _row(**kwargs) -> pd.Series:
    defaults = {"min_amount": None, "max_amount": None, "currency": "USD", "interval": "yearly"}
    return pd.Series({**defaults, **kwargs})


def test_format_salary_both_amounts():
    row = _row(min_amount=100_000, max_amount=140_000, currency="USD", interval="yearly")
    assert _format_salary(row) == "$100,000–$140,000/yr"


def test_format_salary_min_only():
    row = _row(min_amount=80_000, max_amount=None, currency="USD", interval="yearly")
    assert _format_salary(row) == "$80,000+/yr"


def test_format_salary_max_only():
    row = _row(min_amount=None, max_amount=120_000, currency="USD", interval="yearly")
    assert _format_salary(row) == "up to $120,000/yr"


def test_format_salary_missing():
    row = _row(min_amount=None, max_amount=None)
    assert _format_salary(row) == ""


def test_format_salary_hourly():
    row = _row(min_amount=25, max_amount=35, currency="USD", interval="hourly")
    assert _format_salary(row) == "$25–$35/hr"


def test_format_salary_non_usd():
    row = _row(min_amount=50_000, max_amount=70_000, currency="GBP", interval="yearly")
    assert _format_salary(row) == "GBP 50,000–70,000/yr"


# ── _row_to_jd ────────────────────────────────────────────────────────────────

def _full_row(**kwargs) -> pd.Series:
    defaults = {
        "title": "ML Engineer",
        "company": "Acme Corp",
        "location": "San Francisco, CA",
        "job_url": "https://www.linkedin.com/jobs/view/123",
        "description": "Build ML pipelines.",
        "min_amount": None,
        "max_amount": None,
        "currency": "USD",
        "interval": "yearly",
    }
    return pd.Series({**defaults, **kwargs})


def test_row_to_jd_maps_all_fields():
    row = _full_row(min_amount=120_000, max_amount=160_000)
    jd = _row_to_jd(row)
    assert jd["title"] == "ML Engineer"
    assert jd["company"] == "Acme Corp"
    assert jd["location"] == "San Francisco, CA"
    assert jd["url"] == "https://www.linkedin.com/jobs/view/123"
    assert jd["description"] == "Build ML pipelines."
    assert jd["salary"] == "$120,000–$160,000/yr"


def test_row_to_jd_nan_fields_become_empty_string():
    row = _full_row(location=float("nan"), description=float("nan"))
    jd = _row_to_jd(row)
    assert jd["location"] == ""
    assert jd["description"] == ""


def test_row_to_jd_no_description_excluded():
    """Rows with empty description should be excluded by the fetch() caller, not _row_to_jd itself."""
    row = _full_row(description="")
    jd = _row_to_jd(row)
    assert jd["description"] == ""  # _row_to_jd doesn't filter — fetch() does


# ── fetch() ───────────────────────────────────────────────────────────────────

def _make_df(rows: list[dict]) -> pd.DataFrame:
    cols = ["title", "company", "location", "job_url", "description",
            "min_amount", "max_amount", "currency", "interval"]
    records = []
    for r in rows:
        rec = {c: r.get(c, None) for c in cols}
        records.append(rec)
    return pd.DataFrame(records)


def test_fetch_returns_jd_list():
    df = _make_df([
        {"title": "SWE", "company": "Beta", "location": "Remote",
         "job_url": "https://example.com/1", "description": "Code stuff."},
        {"title": "PM", "company": "Gamma", "location": "NYC",
         "job_url": "https://example.com/2", "description": "Manage products."},
    ])
    with patch("scripts.fetch_jds.scrape_jobs", return_value=df):
        result = fetch("engineer", location="Remote", sites=["linkedin"], results_wanted=2)
    assert len(result) == 2
    assert result[0]["title"] == "SWE"
    assert result[1]["title"] == "PM"


def test_fetch_drops_rows_without_title_or_description():
    df = _make_df([
        {"title": "", "company": "X", "description": "Something"},
        {"title": "Engineer", "company": "Y", "description": ""},
        {"title": "Designer", "company": "Z", "description": "Design things."},
    ])
    with patch("scripts.fetch_jds.scrape_jobs", return_value=df):
        result = fetch("designer", location="Remote", sites=["indeed"], results_wanted=3)
    assert len(result) == 1
    assert result[0]["title"] == "Designer"


def test_fetch_empty_dataframe():
    df = _make_df([])
    with patch("scripts.fetch_jds.scrape_jobs", return_value=df):
        result = fetch("xyz", location="Remote", sites=["linkedin"], results_wanted=5)
    assert result == []
```

- [ ] **Step 2: Run tests — verify they FAIL (module doesn't exist yet)**

```bash
cd backend && python -m pytest tests/test_fetch_jds.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'scripts.fetch_jds'`

- [ ] **Step 3: Commit the failing tests**

```bash
git add backend/tests/test_fetch_jds.py
git commit -m "test(fetch-jds): add failing unit tests for jobspy mapping helpers"
```

---

### Task 3: Implement scripts/fetch_jds.py

**Files:**
- Create: `scripts/fetch_jds.py`

**Interfaces:**
- Consumes: `jobspy.scrape_jobs` (from `python-jobspy`), `app.config.get_settings` (for default path hint)
- Produces:
  - `_format_salary(row: pd.Series) -> str`
  - `_row_to_jd(row: pd.Series) -> dict` with keys `title, company, location, salary, url, description`
  - `fetch(search_term: str, *, location: str, sites: list[str], results_wanted: int, hours_old: int = 72) -> list[dict]`
  - `main()` — CLI entry point

- [ ] **Step 1: Create scripts/fetch_jds.py**

```python
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
```

- [ ] **Step 2: Run the tests — verify they PASS**

```bash
cd backend && python -m pytest tests/test_fetch_jds.py -v
```

Expected output (all green):
```
tests/test_fetch_jds.py::test_format_salary_both_amounts PASSED
tests/test_fetch_jds.py::test_format_salary_min_only PASSED
tests/test_fetch_jds.py::test_format_salary_max_only PASSED
tests/test_fetch_jds.py::test_format_salary_missing PASSED
tests/test_fetch_jds.py::test_format_salary_hourly PASSED
tests/test_fetch_jds.py::test_format_salary_non_usd PASSED
tests/test_fetch_jds.py::test_row_to_jd_maps_all_fields PASSED
tests/test_fetch_jds.py::test_row_to_jd_nan_fields_become_empty_string PASSED
tests/test_fetch_jds.py::test_row_to_jd_no_description_excluded PASSED
tests/test_fetch_jds.py::test_fetch_returns_jd_list PASSED
tests/test_fetch_jds.py::test_fetch_drops_rows_without_title_or_description PASSED
tests/test_fetch_jds.py::test_fetch_empty_dataframe PASSED
12 passed
```

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
cd backend && python -m pytest --tb=short -q
```

Expected: all pre-existing tests still pass, 12 new tests passing.

- [ ] **Step 4: Smoke-test the CLI (dry run — no real network call)**

```bash
cd backend && python scripts/fetch_jds.py --help
```

Expected: usage message printed without errors.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/fetch_jds.py
git commit -m "feat(scripts): fetch JDs via python-jobspy, replacing simulang TS scripts"
```

---

## Self-Review

**Spec coverage:**
- [x] Delete `fetch_jds.ts` → Task 1
- [x] Delete `debug_jd_cards.ts` → Task 1
- [x] Add `python-jobspy` → Task 1
- [x] `scripts/fetch_jds.py` with CLI → Task 3
- [x] Output schema `{"jds": [...]}` → Task 3 (`_row_to_jd`, `main`)
- [x] Tests for mapping helpers → Task 2/3
- [x] Keep `sai_fetch.py` → not deleted (spec says delete TS files only)

**Placeholder scan:** None found — all steps have complete code.

**Type consistency:** `_format_salary(row: pd.Series) -> str` and `_row_to_jd(row: pd.Series) -> dict` are defined in Task 3 and consumed by the same file's `fetch()` and tested in Task 2 — names match exactly.
