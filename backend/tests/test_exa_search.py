"""Tests for the Exa roadmap-data layer (hermetic — EXA_API_KEY cleared in conftest)."""
import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.services import exa_search

client = TestClient(app)


def test_query_builders_are_dynamic_not_hardcoded():
    bus = exa_search._course_query("CDL", "Bus Driver")
    swe = exa_search._course_query("System Design", "Software Engineer at Apple")
    assert "CDL" in bus and "Bus Driver" in bus
    assert "System Design" in swe and "Apple" in swe
    assert bus != swe  # adapts to role + skill, not a fixed prompt
    assert "Bus Driver" in exa_search._certifications_query("Bus Driver")
    assert "Software Engineer" in exa_search._networking_query("Software Engineer")
    assert "2026" in exa_search._events_query("Chef", "Oakland", 2026)


def test_has_exa_false_in_tests():
    assert exa_search.has_exa() is False  # conftest clears EXA_API_KEY


def test_exa_functions_degrade_gracefully_without_key():
    assert asyncio.run(exa_search.exa_resources_by_skill(["Python"], "SWE")) == {}
    assert asyncio.run(exa_search.full_roadmap("SWE", ["Python"], "SF")) is None
    assert asyncio.run(exa_search.courses_for_skill("Python", "SWE")) == []


def test_roadmap_endpoint_without_exa_key_is_graceful():
    response = client.post("/roadmap", json={"target": "Bus Driver", "skills": ["CDL"]})
    assert response.status_code == 200
    body = response.json()
    assert body["exa"] is False and "note" in body


def test_roadmap_endpoint_requires_input():
    response = client.post("/roadmap", json={})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"


def test_health_reports_exa_configured_false_in_tests():
    assert client.get("/health").json()["exa_configured"] is False


def test_people_to_connect_graceful_without_key():
    assert asyncio.run(exa_search.people_to_connect("Software Engineer", "SF")) == []


def test_to_steps_is_ordered_and_reveal_friendly():
    data = {
        "skills": {"CDL": {"courses": [{"title": "c", "url": "u", "type": "course", "why": "w"}], "practice": []}},
        "certifications": [{"title": "cert", "url": "u", "type": "certification", "why": "w"}],
        "events": [],  # empty -> dropped
        "people": [{"title": "p", "url": "u", "type": "person", "why": "w"}],
    }
    steps = exa_search.to_steps(data)
    assert steps[0]["order"] == 1 and steps[0]["locked"] is False  # first step open
    assert steps[0]["kind"] == "skill" and steps[0]["skill"] == "CDL"
    assert all(s["locked"] for s in steps[1:])  # rest start locked (unlock as you go)
    kinds = [s["kind"] for s in steps]
    assert "certifications" in kinds and "people" in kinds and "events" not in kinds
    assert all(s.get("id") for s in steps)  # stable ids for the frontend
