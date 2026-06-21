"""Unit tests for scripts/fetch_jds.py mapping helpers."""
import sys
from pathlib import Path
from unittest.mock import patch
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
