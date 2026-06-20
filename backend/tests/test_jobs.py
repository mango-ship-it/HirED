"""Tests for the JobSpy job-pull system (no network — normalize + endpoints mocked)."""
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.services.jobs import normalize

client = TestClient(app)


def test_normalize_maps_columns_and_filters_incomplete():
    df = pd.DataFrame(
        [
            {"site": "indeed", "title": "SWE Intern", "company": "Acme", "city": "SF",
             "state": "CA", "job_url": "http://x", "description": "Build stuff", "is_remote": False},
            {"site": "indeed", "title": "", "company": "NoTitle", "city": "", "state": "",
             "job_url": "", "description": "", "is_remote": True},  # dropped (no title)
            {"site": "google", "title": "Data Analyst", "company": "Globex",
             "location": "Remote", "job_url": "http://y", "description": "x" * 5000, "is_remote": True},
        ]
    )
    jobs = normalize(df)
    assert len(jobs) == 2  # the empty-title row is filtered out
    assert jobs[0]["title"] == "SWE Intern"
    assert jobs[0]["location"] == "SF, CA"
    assert jobs[0]["url"] == "http://x"
    assert jobs[1]["location"] == "Remote"
    assert len(jobs[1]["description"]) <= 3000  # truncated


def test_get_jobs_empty_when_unseen():
    response = client.get("/jobs/nothing-here-xyz")
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_refresh_requires_target():
    response = client.post("/jobs/refresh", json={})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"


def test_refresh_stores_then_get_reads(monkeypatch):
    import app.routes.jobs as jobs_route
    from app.services.jobs import jobs_key
    from app.services.store import get_store

    async def fake_fetch_and_store(target, **kwargs):
        jobs = [{"title": "SWE", "company": "Acme", "location": "SF, CA",
                 "url": "http://x", "site": "indeed", "description": "d"}]
        await get_store().set_json(jobs_key(target), jobs)
        return jobs

    monkeypatch.setattr(jobs_route, "fetch_and_store_jobs", fake_fetch_and_store)
    posted = client.post("/jobs/refresh", json={"target": "swe"})
    assert posted.status_code == 200 and posted.json()["count"] == 1
    got = client.get("/jobs/swe")
    assert got.json()["count"] == 1 and got.json()["jobs"][0]["company"] == "Acme"
