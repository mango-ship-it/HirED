"""Tests for company-wise LeetCode pull (pure parse + mocked endpoint — no network)."""
from fastapi.testclient import TestClient

from app.main import app
from app.services.leetcode_company import _slug, parse_csv

client = TestClient(app)

_SAMPLE = """ID,URL,Title,Difficulty,Acceptance %,Frequency %
1,https://leetcode.com/problems/two-sum,Two Sum,Easy,57.5%,100.0%
2,https://leetcode.com/problems/add-two-numbers,Add Two Numbers,Medium,48.5%,75.0%
,,,,,
"""


def test_slug_normalizes_company_to_repo_folder():
    assert _slug("Goldman Sachs") == "goldman-sachs"
    assert _slug("Google") == "google"
    assert _slug("  JPMorgan Chase & Co. ") == "jpmorgan-chase-co"


def test_parse_csv_extracts_problems_and_skips_blank_rows():
    problems = parse_csv(_SAMPLE)
    assert len(problems) == 2  # blank row dropped
    assert problems[0]["title"] == "Two Sum"
    assert problems[0]["url"].endswith("/two-sum")
    assert problems[0]["difficulty"] == "Easy"
    assert problems[0]["frequency"] == "100.0%"


def test_parse_csv_respects_limit():
    assert len(parse_csv(_SAMPLE, limit=1)) == 1


def test_leetcode_endpoint_returns_problems(monkeypatch):
    import app.routes.learning as learning_route

    async def fake_fetch(company, **kwargs):
        return [{"id": "1", "title": "Two Sum", "url": "x", "difficulty": "Easy",
                 "acceptance": "57%", "frequency": "100%"}]

    monkeypatch.setattr(learning_route, "fetch_company_problems", fake_fetch)
    body = client.get("/leetcode/google").json()
    assert body["count"] == 1 and body["problems"][0]["title"] == "Two Sum"


def test_leetcode_endpoint_unknown_company(monkeypatch):
    import app.routes.learning as learning_route

    async def fake_fetch(company, **kwargs):
        return None

    monkeypatch.setattr(learning_route, "fetch_company_problems", fake_fetch)
    body = client.get("/leetcode/not-a-real-company-xyz").json()
    assert body["count"] == 0 and "note" in body


def test_learning_plan_endpoint_coding_adds_company_practice(monkeypatch):
    import app.routes.learning as learning_route

    async def fake_fetch(company, **kwargs):
        return [{"id": "1", "title": "Two Sum", "url": "x"}]

    async def fake_detect(text):
        return "google"

    monkeypatch.setattr(learning_route, "fetch_company_problems", fake_fetch)
    monkeypatch.setattr(learning_route, "detect_company", fake_detect)
    data = client.post(
        "/learning-plan",
        json={"target": "Software Engineer at Google", "skills": ["Python"]},
    ).json()
    assert data["company_practice"]["company"] == "google"
    assert data["company_practice"]["problems"][0]["title"] == "Two Sum"
