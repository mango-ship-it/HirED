"""Resilient extraction + lesson generation: Claude when keyed, heuristic otherwise.

This is the seam that lets the first page work with NO API key. Each function
prefers Claude (better quality) when ANTHROPIC_API_KEY is set, and falls back to
the dependency-free heuristic on a missing key or any Claude error — so /score
never hard-fails on configuration.
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.models.extraction import ExtractedProfile
from app.models.schemas import Lesson
from app.services.heuristic_extractor import (
    extract_profile_heuristic,
    heuristic_lessons,
)

logger = logging.getLogger("hired.extractor")


async def extract_profile(resume: str, target: str) -> ExtractedProfile:
    """Structured profile from resume + target. Claude if available, else heuristic."""
    if get_settings().anthropic_api_key:
        try:
            from app.services.claude_service import get_claude_service

            return await get_claude_service().extract_profile(resume, target)
        except Exception:
            logger.exception("Claude extraction failed; using heuristic fallback")
    return extract_profile_heuristic(resume, target)


async def generate_lessons(
    *,
    resume: str,
    target: str,
    category_scores: dict[str, int],
    profile: ExtractedProfile,
) -> list[Lesson]:
    """1-3 lessons for the weakest categories. Claude if available, else templated."""
    if get_settings().anthropic_api_key:
        try:
            from app.services.claude_service import get_claude_service

            return await get_claude_service().generate_lessons(
                resume=resume,
                target=target,
                categories=category_scores,
                profile=profile,
            )
        except Exception:
            logger.exception("Claude lesson generation failed; using heuristic fallback")
    return heuristic_lessons(category_scores)
