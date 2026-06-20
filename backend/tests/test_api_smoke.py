"""Integration smoke tests for the API contract — no network, no API keys.

With no ANTHROPIC_API_KEY in the test env, /score runs the heuristic extractor +
deterministic scorer end-to-end. That's the point: the first page works with zero
config, so these tests double as proof the frontend is unblocked.
"""
import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_TARGET = json.dumps(
    {"type": "role", "value": "Data Analyst — needs SQL, Python, and Tableau"}
)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["claude_configured"] is False  # no key in test env -> heuristic path


def test_score_returns_contract_shape_with_no_api_key():
    response = client.post(
        "/score",
        data={
            "user_id": "u1",
            "target": _TARGET,
            "resume_text": "Experienced Python developer. Built dashboards, led a team, grew signups 30%.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["score"] <= 100
    # categories keyed by snake_case scoring category, each {score, weight}
    assert "skills_match" in body["categories"]
    assert set(body["categories"]["skills_match"]) == {"score", "weight"}
    # lessons use the contract field names (heuristic templates populate them)
    assert body["lessons"], "expected at least one lesson"
    assert set(body["lessons"][0]) == {"category", "principle", "example", "action"}
    # surfaced skills power the "what the top tier has that you don't" UI
    assert "Python" in body["matched_skills"]
    assert "SQL" in body["missing_skills"]
    assert body["status"] == {"scoring": "complete", "benchmark": "pending", "resources": "pending"}


def test_score_accepts_file_upload():
    response = client.post(
        "/score",
        data={"user_id": "u1", "target": json.dumps({"type": "role", "value": "Software Engineer"})},
        files={"resume_file": ("resume.txt", b"Jane Doe\nPython, SQL, Airflow developer", "text/plain")},
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
