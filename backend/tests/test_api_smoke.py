"""Integration smoke tests for the API contract — no network, no API keys.

Verifies the app boots, routes are wired, request validation works, `/score`
returns the API_CONTRACT.md shape (with Claude mocked), and the Fetch.ai agent
routes fall back gracefully when no agent is configured (the demo-safety path).
"""
import json

from fastapi.testclient import TestClient

from app.main import app
from app.models.extraction import ExtractedProfile
from app.models.schemas import Lesson

client = TestClient(app)

_TARGET = json.dumps({"type": "role", "value": "Software Engineering Internship"})


class _FakeClaude:
    """Deterministic stand-in for ClaudeService so /score runs without a network."""

    async def extract_profile(self, resume: str, target: str) -> ExtractedProfile:
        return ExtractedProfile(
            required_skills=["python", "sql", "airflow"],
            matched_skills=["python", "sql"],
            missing_skills=["airflow"],
            quantified_achievement_count=2,
            total_achievement_count=5,
            years_experience=2.0,
            education_level="bachelor",
            clarity_signal=0.6,
            target_summary="Software Engineering Internship",
        )

    async def generate_lessons(self, *, resume, target, categories, profile):
        return [
            Lesson(
                category="quantified_achievements",
                principle="Recruiters scan for numbers.",
                example="Before: 'helped' -> After: 'cut latency 30%'.",
                action="Add a metric to bullet 2.",
            )
        ]


def _mock_claude(monkeypatch):
    import app.routes.score as score_route

    monkeypatch.setattr(score_route, "get_claude_service", lambda: _FakeClaude())


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["claude_configured"] is False


def test_score_returns_contract_shape(monkeypatch):
    _mock_claude(monkeypatch)
    response = client.post(
        "/score",
        data={"user_id": "u1", "target": _TARGET, "resume_text": "Jane Doe. Python, SQL."},
    )
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["score"] <= 100
    # categories keyed by snake_case scoring category, each {score, weight}
    assert "skills_match" in body["categories"]
    assert set(body["categories"]["skills_match"]) == {"score", "weight"}
    # lessons use the contract field names
    assert set(body["lessons"][0]) == {"category", "principle", "example", "action"}
    # per-section status
    assert body["status"] == {"scoring": "complete", "benchmark": "pending", "resources": "pending"}
    # surfaced skills power the "what the top tier has that you don't" UI
    assert "python" in body["matched_skills"]
    assert body["missing_skills"] == ["airflow"]


def test_score_accepts_file_upload(monkeypatch):
    _mock_claude(monkeypatch)
    response = client.post(
        "/score",
        data={"user_id": "u1", "target": _TARGET},
        files={"resume_file": ("resume.txt", b"Jane Doe\nPython, SQL, Airflow", "text/plain")},
    )
    assert response.status_code == 200
    assert "skills_match" in response.json()["categories"]


def test_score_missing_resume_returns_invalid_input():
    response = client.post("/score", data={"user_id": "u1", "target": _TARGET})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"


def test_score_bad_target_json_returns_invalid_input():
    response = client.post(
        "/score", data={"user_id": "u1", "target": "not-json", "resume_text": "hi"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"


def test_score_missing_required_fields_is_422():
    # No user_id / target at all -> FastAPI form validation.
    assert client.post("/score", data={}).status_code == 422


def test_benchmark_falls_back_without_agent():
    response = client.post(
        "/benchmark",
        json={"user_id": "u1", "score": 70, "target": {"type": "role", "value": "Data Analyst"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["percentile"] <= 100
    assert body["sample_size"] >= 0
    assert isinstance(body["message"], str) and body["message"]


def test_benchmark_requires_target_object():
    # Old shape (target as a bare string) must now fail validation.
    response = client.post("/benchmark", json={"user_id": "u1", "score": 70, "target": "Data Analyst"})
    assert response.status_code == 422


def test_resources_falls_back_without_agent():
    response = client.post(
        "/resources",
        json={
            "user_id": "u1",
            "gap_category": "skills_match",
            "context": {"first_gen": True, "target_type": "tech_internship"},
        },
    )
    assert response.status_code == 200
    resources = response.json()["resources"]
    assert isinstance(resources, list) and resources
    assert set(resources[0]) == {"name", "url", "description"}


def test_narrate_requires_nonempty_text():
    assert client.post("/narrate", json={"text": ""}).status_code == 422
