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


def test_root_ok():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "HirED API"


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


def test_score_uses_real_jd_skills_when_jobs_cached():
    """Accuracy bridge: cached real postings override the guessed required-skills."""
    import asyncio

    from app.services.jobs import jobs_key
    from app.services.store import get_store

    target_value = "swe-jd-bridge-test"
    asyncio.run(
        get_store().set_json(
            jobs_key(target_value),
            [
                {"title": "SWE", "description": "We need Python, AWS, and Docker experience."},
                {"title": "SWE", "description": "Python and AWS required; Kubernetes a plus."},
            ],
        )
    )
    response = client.post(
        "/score",
        data={
            "user_id": "jd-user",
            "target": json.dumps({"type": "role", "value": target_value}),
            "resume_text": "Experienced developer skilled in Python and SQL. Built web apps.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    # required skills now come from the REAL postings: Python matched, AWS missing
    assert "Python" in body["matched_skills"]
    assert "AWS" in body["missing_skills"]


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


def test_benchmark_response_includes_matches_field():
    """Contract: /benchmark response always carries a `matches` array (empty on fallback)."""
    response = client.post("/benchmark", json={
        "user_id": "smoke-user",
        "score": 60,
        "target": {"type": "role", "value": "Software Engineering Internship"},
    })
    assert response.status_code == 200
    data = response.json()
    assert "matches" in data
    assert isinstance(data["matches"], list)
    # No agent running in the test → fallback path → empty list
    assert data["matches"] == []


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


def test_score_remembers_user_profile():
    uid = "tester-remember-1"
    scored = client.post(
        "/score",
        data={"user_id": uid, "target": _TARGET, "resume_text": "Python and SQL developer"},
    )
    assert scored.status_code == 200
    saved = client.get(f"/profile/{uid}")
    assert saved.status_code == 200
    body = saved.json()
    assert body["user_id"] == uid
    assert "missing_skills" in body and "profile" in body


def test_profile_unknown_user_is_404():
    assert client.get("/profile/nobody-xyz").status_code == 404


def test_progress_save_and_load_roundtrip():
    client.post("/progress", json={"user_id": "u-prog", "progress": {"unlocked": [1, 2], "done": [1]}})
    body = client.get("/progress/u-prog").json()
    assert body["progress"] == {"unlocked": [1, 2], "done": [1]}  # persisted per user


def test_progress_requires_user_id_and_progress():
    assert client.post("/progress", json={"progress": {}}).status_code == 400
    assert client.post("/progress", json={"user_id": "x"}).status_code == 400


def test_progress_empty_for_unseen_user():
    assert client.get("/progress/never-seen-xyz").json()["progress"] == {}
