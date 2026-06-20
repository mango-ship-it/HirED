"""Integration smoke tests for the locked API contract — no external services.

Verifies the app boots, routes are wired, request validation works, and the
Fetch.ai agent routes fall back gracefully when no agent is configured. These
run with NO API keys and NO agents running — i.e. the demo-safety path.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # No secrets configured in the test env -> all booleans report False.
    assert body["claude_configured"] is False
    assert body["benchmark_agent_configured"] is False


def test_score_requires_fields():
    # Missing resume/target -> pydantic validation error, not a crash.
    assert client.post("/score", json={}).status_code == 422


def test_benchmark_falls_back_without_agent():
    response = client.post(
        "/benchmark", json={"score": 70, "target": "Data Analyst at Acme"}
    )
    assert response.status_code == 200
    percentile = response.json()["percentile"]
    assert 0 <= percentile <= 100


def test_resources_falls_back_without_agent():
    response = client.post(
        "/resources", json={"gap_category": "skills_match", "context": ""}
    )
    assert response.status_code == 200
    resources = response.json()["resources"]
    assert isinstance(resources, list) and resources


def test_narrate_requires_nonempty_text():
    assert client.post("/narrate", json={"text": ""}).status_code == 422
