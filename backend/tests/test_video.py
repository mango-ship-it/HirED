"""Tests for the Pika /video endpoints (hermetic — FAL_KEY cleared in conftest)."""
from fastapi.testclient import TestClient

from app.main import app
from app.services.pika_video import build_video_prompt

client = TestClient(app)


def test_build_video_prompt_includes_role_and_skill():
    prompt = build_video_prompt("Bus Driver", ["CDL", "Defensive Driving"])
    assert "Bus Driver" in prompt and "CDL" in prompt


def test_video_unconfigured_without_fal_key():
    assert client.post("/video", json={"role": "Nurse"}).json()["status"] == "unconfigured"
    assert client.get("/video/abc123").json()["status"] == "unconfigured"


def test_health_reports_fal_configured_false_in_tests():
    assert client.get("/health").json()["fal_configured"] is False
