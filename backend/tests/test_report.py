"""Tests for the templated report + slide generation and the /report endpoint."""
import json

from fastapi.testclient import TestClient

from app.main import app
from app.models.report import ReportRequest
from app.models.schemas import CategoryBreakdown, Lesson, Target
from app.services.report_service import build_report

client = TestClient(app)


def _request() -> ReportRequest:
    return ReportRequest(
        user_id="u1",
        target=Target(type="role", value="Marketing Coordinator"),
        score=58,
        categories={
            "skills_match": CategoryBreakdown(score=65, weight=0.35),
            "quantified_achievements": CategoryBreakdown(score=30, weight=0.25),
            "experience": CategoryBreakdown(score=80, weight=0.20),
            "education": CategoryBreakdown(score=90, weight=0.10),
            "clarity": CategoryBreakdown(score=50, weight=0.10),
        },
        lessons=[
            Lesson(category="quantified_achievements", principle="p", example="e", action="Add a metric.")
        ],
        matched_skills=["Social Media"],
        missing_skills=["Google Analytics", "A/B Testing"],
        percentile=40,
    )


def test_build_report_is_templated_and_complete():
    report = build_report(_request())
    assert report.summary
    assert any("Quantified" in w for w in report.weaknesses)  # 30 < 60 -> a gap
    assert any("Experience" in s or "Education" in s for s in report.strengths)  # >= 70
    assert report.next_steps == ["Add a metric."]
    assert report.jobs and report.mentors  # pulled from the Sai seed
    assert report.slides and report.slides[0].index == 0
    # each gap lesson becomes its own slide
    assert any(s.title == "Quantified Impact" for s in report.slides)
    # slides carry narratable text for TTS
    assert all(s.speaker_notes for s in report.slides)


def test_report_endpoint_returns_contract_shape():
    body = json.loads(_request().model_dump_json())
    response = client.post("/report", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["summary"] and data["slides"]
    assert set(data["slides"][0]) >= {"index", "title", "body", "speaker_notes"}
    assert data["jobs"] and data["mentors"]
