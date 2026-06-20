"""Models for the detailed report / summary page (the 3rd page).

`/report` assembles a narrative report + slide deck from the data the frontend
already collected (score, categories, lessons, skills, percentile, resources) plus
Sai-sourced jobs/mentors. Generation is templated (no API spend); see report_service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.schemas import CategoryBreakdown, Lesson, Resource, Target


class Job(BaseModel):
    title: str
    company: str
    location: str = ""
    url: str = ""


class Mentor(BaseModel):
    name: str
    role: str = ""
    company: str = ""
    url: str = ""
    why: str = ""


class Slide(BaseModel):
    index: int
    title: str
    body: str
    speaker_notes: str = ""  # narratable text for TTS (/narrate)


class ReportRequest(BaseModel):
    """What the frontend POSTs — the pieces it already has from /score, /benchmark,
    /resources. Passing them avoids re-running (and re-billing) extraction/scoring."""

    user_id: str = Field(min_length=1)
    target: Target
    score: int = Field(ge=0, le=100)
    categories: dict[str, CategoryBreakdown] = Field(default_factory=dict)
    lessons: list[Lesson] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    percentile: int | None = Field(default=None, ge=0, le=100)
    resources: list[Resource] = Field(default_factory=list)


class ReportResponse(BaseModel):
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    next_steps: list[str]
    jobs: list[Job]
    mentors: list[Mentor]
    slides: list[Slide]
