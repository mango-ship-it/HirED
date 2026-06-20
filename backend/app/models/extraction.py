"""Internal structured profile extracted by Claude (NOT the API contract).

Claude fills this in from the resume + target. Our deterministic scorer consumes
it. Claude never produces the score itself (see MASTER.md §7).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedProfile(BaseModel):
    """Structured facts pulled from the resume + parsed target.

    All numeric fields are raw counts/years; normalization to 0..1 happens in the
    scorer, not here. Keeping extraction and scoring separate is what makes the
    score deterministic and trustworthy.
    """

    # Skills
    required_skills: list[str] = Field(
        default_factory=list,
        description="Skills the target role requires, parsed from the target text",
    )
    matched_skills: list[str] = Field(
        default_factory=list,
        description="Required skills the candidate demonstrably has",
    )
    missing_skills: list[str] = Field(
        default_factory=list,
        description="Required skills the candidate is missing",
    )

    # Quantified achievements
    quantified_achievement_count: int = Field(
        default=0, ge=0,
        description="Number of bullets with concrete numbers/metrics/impact",
    )
    total_achievement_count: int = Field(
        default=0, ge=0,
        description="Total number of experience bullets/achievements found",
    )

    # Experience
    years_experience: float = Field(
        default=0.0, ge=0,
        description="Approximate total years of relevant experience",
    )

    # Education
    education_level: str = Field(
        default="none",
        description="One of: none, some, certificate, associate, bachelor, master, doctorate",
    )

    # Clarity signals (0..1, Claude's qualitative read of writing clarity)
    clarity_signal: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="0..1 read of resume clarity: action verbs, structure, concision",
    )

    # Human-readable target summary for the benchmark/resources context
    target_summary: str = Field(
        default="", description="One-line summary of the parsed target role"
    )


# JSON Schema fed to Claude's structured-output (output_config.format). Kept here
# so the extraction shape and the prompt schema can't drift apart.
EXTRACTION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "matched_skills": {"type": "array", "items": {"type": "string"}},
        "missing_skills": {"type": "array", "items": {"type": "string"}},
        "quantified_achievement_count": {"type": "integer"},
        "total_achievement_count": {"type": "integer"},
        "years_experience": {"type": "number"},
        "education_level": {
            "type": "string",
            "enum": [
                "none", "some", "certificate", "associate",
                "bachelor", "master", "doctorate",
            ],
        },
        "clarity_signal": {"type": "number"},
        "target_summary": {"type": "string"},
    },
    "required": [
        "required_skills",
        "matched_skills",
        "missing_skills",
        "quantified_achievement_count",
        "total_achievement_count",
        "years_experience",
        "education_level",
        "clarity_signal",
        "target_summary",
    ],
    "additionalProperties": False,
}
