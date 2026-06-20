"""Tests for the Sai data-ingestion seam (reads an exported JSON file)."""
from app.models.report import Job, Mentor
from app.services import sai_gateway


def test_load_jobs_from_seed():
    jobs = sai_gateway.load_jobs("Marketing Coordinator")
    assert jobs and all(isinstance(j, Job) for j in jobs)
    assert jobs[0].title and jobs[0].company


def test_load_mentors_from_seed():
    mentors = sai_gateway.load_mentors("Marketing Coordinator")
    assert mentors and all(isinstance(m, Mentor) for m in mentors)


def test_missing_file_returns_empty(monkeypatch, tmp_path):
    missing = str(tmp_path / "nope.json")
    monkeypatch.setattr(
        sai_gateway, "get_settings", lambda: type("S", (), {"sai_data_path": missing})()
    )
    assert sai_gateway.load_jobs("x") == []
    assert sai_gateway.load_mentors("x") == []
