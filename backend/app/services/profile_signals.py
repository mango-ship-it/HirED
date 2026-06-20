"""Adapter: ExtractedProfile (Claude's facts) -> normalized 0..1 signals dict.

Keeps the LLM-extraction layer and the deterministic scorer (app.scoring) cleanly
separated. The output dict has exactly the keys app.scoring.WEIGHTS expects, so it
feeds straight into compute_score(). Pure function — no mutation.
"""

from __future__ import annotations

from app.models.extraction import ExtractedProfile
from app.scoring import (
    education_signal,
    experience_signal,
    quantified_signal,
    skills_match_signal,
)

# Education labels coming out of Claude's enum -> app.scoring's ladder keys.
# (Claude is prompted with: none|some|certificate|associate|bachelor|master|doctorate;
# app.scoring's ladder uses: none|high_school|some_college|associate|bachelor|master|doctorate.)
_EDUCATION_ALIASES: dict[str, str] = {
    "none": "none",
    "some": "some_college",
    "certificate": "some_college",
    "associate": "associate",
    "bachelor": "bachelor",
    "master": "master",
    "doctorate": "doctorate",
}


def profile_to_signals(profile: ExtractedProfile) -> dict[str, float]:
    """Convert an ExtractedProfile into the 0..1 signals dict compute_score expects."""
    edu_key = _EDUCATION_ALIASES.get(profile.education_level.strip().lower(), "none")

    return {
        "skills_match": skills_match_signal(
            matched=len(profile.matched_skills),
            required=len(profile.required_skills),
        ),
        "quantified_achievements": quantified_signal(profile.quantified_achievement_count),
        "experience": experience_signal(profile.years_experience),
        "education": education_signal(edu_key),
        # clarity_signal is already a 0..1 read from extraction; compute_score clamps it.
        "clarity": profile.clarity_signal,
    }
