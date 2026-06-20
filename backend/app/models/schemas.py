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
# /score  (API_CONTRACT.md: multipart upload in; these model the JSON response)
# --------------------------------------------------------------------------- #


class Target(BaseModel):
    """The user's goal. Sent on /score as a JSON string field in the multipart form."""

    type: str = Field(description='"role" | "school" | "job_posting_text"')
    value: str = Field(min_length=1, description="e.g. 'Software Engineering Internship'")


class Lesson(BaseModel):
    """One micro-lesson for a gap: principle -> example -> action (API_CONTRACT.md).

    `category` is the snake_case scoring category (e.g. "quantified_achievements")
    so the frontend can fetch resources for it via /resources.
    """

    category: str
    principle: str
    example: str
    action: str


class CategoryBreakdown(BaseModel):
    """Per-category breakdown: 0-100 score + its weight in the formula (§7)."""

    score: int = Field(ge=0, le=100)
    weight: float


class ScoreStatus(BaseModel):
    """Per-section readiness (API_CONTRACT.md). `/score` returns scoring
    synchronously; benchmark/resources come from their own endpoints, so they
    start "pending" and the frontend renders them when ready."""

    scoring: str = "complete"
    benchmark: str = "pending"
    resources: str = "pending"


class ScoreResponse(BaseModel):
    """Output of /score (API_CONTRACT.md).

    `categories` maps each snake_case scoring category (skills_match,
    quantified_achievements, experience, education, clarity) -> {score, weight}.
    `lessons` are the 1-3 gaps that move the needle; `status` tells the frontend
    which sections are ready.
    """

    score: int = Field(ge=0, le=100)
    categories: dict[str, CategoryBreakdown]
    lessons: list[Lesson]
    status: ScoreStatus = Field(default_factory=ScoreStatus)


# --------------------------------------------------------------------------- #
# /benchmark
# --------------------------------------------------------------------------- #


class BenchmarkRequest(BaseModel):
    user_id: str = Field(min_length=1, description="Same client-generated UUID sent to /score")
    score: int = Field(ge=0, le=100)
    target: Target


class BenchmarkResponse(BaseModel):
    percentile: int = Field(ge=0, le=100)
    sample_size: int = Field(ge=0, description="Size of the comparison cohort")
    message: str = Field(description="Motivating, plain-language framing of the percentile")


# --------------------------------------------------------------------------- #
# /resources
# --------------------------------------------------------------------------- #


class ResourceContext(BaseModel):
    """Optional tailoring signals (API_CONTRACT.md)."""

    first_gen: bool = False
    target_type: str = ""


class ResourcesRequest(BaseModel):
    user_id: str = Field(min_length=1, description="Same client-generated UUID sent to /score")
    gap_category: str = Field(min_length=1)
    context: ResourceContext = Field(default_factory=ResourceContext)


class Resource(BaseModel):
    name: str
    url: str
    description: str


class ResourcesResponse(BaseModel):
    resources: list[Resource]


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
