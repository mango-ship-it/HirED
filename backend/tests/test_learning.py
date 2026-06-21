"""Tests for the domain-agnostic learning plan + /learning-plan endpoint."""
from fastapi.testclient import TestClient

from app.main import app
from app.services.learning_plan import build_plan, resources_for_skill

client = TestClient(app)


def test_resources_for_skill_non_coding_uses_real_search_links():
    cards = resources_for_skill("Knife Skills", location="Oakland, CA", coding=False)
    types = {c["type"] for c in cards}
    assert {"video", "course", "local"} <= types
    assert "practice" not in types  # no LeetCode for a non-coding skill
    assert all(c["url"].startswith("https://") for c in cards)
    assert any("near" in c["title"].lower() for c in cards)


def test_build_plan_detects_coding_and_adds_leetcode():
    plan = build_plan(["Python", "SQL"], role="Software Engineer", location="SF")
    assert plan["is_coding"] is True
    assert any(c["type"] == "practice" for c in plan["items"][0]["resources"])
    assert plan["role_resources"]  # certifications + local
    assert "credential_note" in plan["items"][0]


def test_build_plan_chef_is_not_coding_and_has_no_leetcode():
    plan = build_plan(["Food Safety", "Plating"], role="Chef", location="Oakland")
    assert plan["is_coding"] is False
    assert all(
        c["type"] != "practice" for item in plan["items"] for c in item["resources"]
    )


def test_learning_plan_endpoint_with_explicit_skills():
    response = client.post(
        "/learning-plan",
        json={"target": "Bus Driver", "location": "Oakland, CA", "skills": ["CDL", "Defensive Driving"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["skill"] == "CDL"
    assert data["is_coding"] is False


def test_learning_plan_endpoint_requires_some_input():
    response = client.post("/learning-plan", json={})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"
