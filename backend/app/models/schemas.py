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
    """Per-category breakdown: 0-100 score + its weight + a short why-it-scored-that note."""

    score: int = Field(ge=0, le=100)
    weight: float
    explanation: str = Field(default="", description="Short plain-language reason for this score")


class ScoreStatus(BaseModel):
    """Per-section readiness (API_CONTRACT.md). `/score` returns scoring
    synchronously; benchmark/resources come from their own endpoints, so they
    start "pending" and the frontend renders them when ready."""

    scoring: str = "complete"
    benchmark: str = "pending"
    resources: str = "pending"


class Annotation(BaseModel):
    """A resume excerpt the score references — powers breakdown-page highlighting."""

    quote: str = Field(description="VERBATIM text from the resume; match against resume_text to highlight")
    category: str = Field(description="Which scoring category it affects (snake_case)")
    sentiment: str = Field(description='"positive" (strengthens) or "negative" (a gap)')
    reason: str = Field(default="", description="Short why")


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
    matched_skills: list[str] = Field(
        default_factory=list, description="Target skills the candidate already has"
    )
    missing_skills: list[str] = Field(
        default_factory=list,
        description="Target skills the candidate lacks — powers 'what the top tier has that you don't'",
    )
    resume_text: str = Field(
        default="",
        description="Full extracted resume text — the frontend renders it and matches annotations against it",
    )
    has_resume: bool = Field(
        default=False,
        description="True when a real resume was scored — gate the side-by-side resume view on this",
    )
    annotations: list[Annotation] = Field(
        default_factory=list,
        description="Verbatim resume excerpts the score references (breakdown-page highlighting)",
    )
    status: ScoreStatus = Field(default_factory=ScoreStatus)


# --------------------------------------------------------------------------- #
# /benchmark
# --------------------------------------------------------------------------- #


class BenchmarkRequest(BaseModel):
    user_id: str = Field(min_length=1, description="Same client-generated UUID sent to /score")
    score: int = Field(ge=0, le=100)
    target: Target


class Match(BaseModel):
    """One 2AFC head-to-head: a synthetic competitor and whether the user won."""

    competitor_headline: str = Field(description="First line of the synthesized resume")
    competitor_resume: str = Field(description="Full synthesized resume text — label as AI-generated on the FE")
    user_won: bool


class Candidate(BaseModel):
    """A real professional in the target role, shown on the 'How you compare' page."""

    name: str
    url: str
    why_stronger: str = Field(default="", description="One sentence: what makes them a strong candidate")
    score: int = Field(default=0, ge=0, le=100, description="Deterministic 0-100 strength — plot on the scale")


class BenchmarkResponse(BaseModel):
    percentile: int = Field(ge=0, le=100)
    sample_size: int = Field(ge=0, description="Size of the comparison cohort")
    message: str = Field(description="Motivating, plain-language framing of the percentile")
    matches: list[Match] = Field(
        default_factory=list,
        description="Per-2AFC results (Fetch.ai agent). Empty when using the real-candidate path.",
    )
    candidates: list[Candidate] = Field(
        default_factory=list, description="Real professionals in this role (page 6 — Exa)"
    )
    transparency: str = Field(
        default="", description="Plain-language explanation of how the percentile/comparison is computed"
    )


# --------------------------------------------------------------------------- #
# /resources
# --------------------------------------------------------------------------- #


class ResourceContext(BaseModel):
    """Optional tailoring signals (API_CONTRACT.md)."""

    first_gen: bool = False
    target_type: str = ""


class ResourcesRequest(BaseModel):
    # user_id is optional; `context` accepts the target ROLE as a plain string
    # (what the frontend sends, e.g. "PGA golf coach") OR the structured object form.
    user_id: str = ""
    gap_category: str = Field(min_length=1)
    context: ResourceContext | str | None = None


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
