"""Tests for the grounded JD digest injected into the lessons prompt."""
import asyncio

from app.models.extraction import ExtractedProfile
from app.services.extractor import generate_lessons
from app.services.jd_context import build_lesson_context

_JOBS = [
    {"title": "Data Analyst",
     "description": "We need strong SQL experience. Build dashboards in Tableau. Free snacks daily."},
    {"title": "Senior Data Analyst",
     "description": "3+ years experience with Python required. We are an equal opportunity employer."},
    {"title": "Data Analyst", "description": "duplicate-title posting with no clean requirement."},
]


def test_digest_has_sample_size_titles_and_relevant_excerpts():
    ctx = build_lesson_context(_JOBS, ["SQL", "Python"])
    assert "across 3 postings" in ctx
    assert "Data Analyst" in ctx and "Senior Data Analyst" in ctx
    # relevance filter keeps skill+cue lines, drops perks/boilerplate
    assert "SQL" in ctx or "Python" in ctx
    assert "snacks" not in ctx.lower()


def test_digest_dedups_exact_duplicate_titles():
    ctx = build_lesson_context(_JOBS, [])
    titles_line = next(line for line in ctx.splitlines() if line.startswith("Posting titles"))
    titles = titles_line.split(": ", 1)[1].split("; ")
    assert titles == ["Data Analyst", "Senior Data Analyst"]  # exact dup removed


def test_digest_empty_for_no_jobs():
    assert build_lesson_context([], ["SQL"]) == ""
    assert build_lesson_context(None) == ""


def test_digest_respects_char_cap():
    big = [{"title": "T", "description": "must have experience. " * 500}]
    assert len(build_lesson_context(big, [], max_chars=400)) <= 400


def test_generate_lessons_accepts_jd_context_on_heuristic_path():
    # No API key in tests -> heuristic path: jd_context is accepted and ignored, no crash.
    lessons = asyncio.run(
        generate_lessons(
            resume="Python and SQL developer",
            target="Data Analyst",
            category_scores={"skills_match": 40, "clarity": 80},
            profile=ExtractedProfile(),
            jd_context="REAL JOB POSTINGS FOR THE TARGET ROLE (across 3 postings):",
        )
    )
    assert lessons  # heuristic still returns templated lessons
