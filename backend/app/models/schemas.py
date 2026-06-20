"""Request/response schemas — the LOCKED API contract from FRONTEND.md.

Do NOT change these shapes; the frontend mocks them exactly:
  POST /score      {resume, target}        -> {score, categories:{...}, lessons:[...]}
  POST /benchmark  {score, target}         -> {percentile}
  POST /resources  {gap_category, context} -> {resources:[...]}
  POST /narrate    {text}                   -> {audio_url}
  POST /transcribe (audio upload)           -> {text}
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# /score
# --------------------------------------------------------------------------- #


class ScoreRequest(BaseModel):
    """Input to /score. `resume` is plain text (chat pitch, pasted resume, or
    transcript). `target` is the company + role text (or a pasted job posting)."""

    resume: str = Field(min_length=1, description="Resume / pitch / transcript text")
    target: str = Field(min_length=1, description="Target company + role text")


class Lesson(BaseModel):
    """A single micro-lesson for one gap: principle -> example -> next step.

    `category` ties the lesson back to a scoring category so the frontend can
    fetch resources for it via /resources.
    """

    category: str
    title: str
    principle: str
    example: str
    next_step: str


class CategoryBreakdown(BaseModel):
    """Per-category breakdown for one scoring category (FRONTEND.md: label every
    score as a learnable skill — 'Quantified Impact: 40/100', never a bare number).

    Matches `app.scoring.ScoreResult.to_payload()`.
    """

    score: int = Field(ge=0, le=100)
    weight: float
    contribution: float


class ScoreResponse(BaseModel):
    """Output of /score.

    `score` is 0-100. `categories` maps each HUMAN-LABELED scoring category
    (e.g. "Skills Match", "Quantified Impact") -> its breakdown (score/weight/
    contribution) for the per-category bars. `lessons` is the 1-3 gaps that move
    the needle. Shape mirrors `app.scoring.ScoreResult.to_payload()`.
    """

    score: int = Field(ge=0, le=100)
    categories: dict[str, CategoryBreakdown]
    lessons: list[Lesson]


# --------------------------------------------------------------------------- #
# /benchmark
# --------------------------------------------------------------------------- #


class BenchmarkRequest(BaseModel):
    score: int = Field(ge=0, le=100)
    target: str = Field(min_length=1)


class BenchmarkResponse(BaseModel):
    percentile: int = Field(ge=0, le=100)


# --------------------------------------------------------------------------- #
# /resources
# --------------------------------------------------------------------------- #


class ResourcesRequest(BaseModel):
    gap_category: str = Field(min_length=1)
    context: str = Field(default="", description="Optional context to tailor results")


class ResourcesResponse(BaseModel):
    resources: list[str]


# --------------------------------------------------------------------------- #
# /narrate
# --------------------------------------------------------------------------- #


class NarrateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class NarrateResponse(BaseModel):
    audio_url: str


# --------------------------------------------------------------------------- #
# /transcribe  (response only; request is a multipart file upload)
# --------------------------------------------------------------------------- #


class TranscribeResponse(BaseModel):
    text: str
