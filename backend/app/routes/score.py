"""POST /score — Claude extract -> deterministic score -> 1-3 lessons.

The single most important endpoint: it must be re-callable with an edited resume
to power the re-score "money shot" (MASTER.md §5). It collapses intake/extract,
target-parse, scoring, and lesson-gen into one call (FRONTEND.md contract).

Scoring uses app.scoring (deterministic, pure Python, TDD-covered). Claude only
extracts the raw signals and writes the teaching copy — it never invents the number.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import ScoreRequest, ScoreResponse
from app.scoring import compute_score
from app.services.claude_service import get_claude_service
from app.services.profile_signals import profile_to_signals

logger = logging.getLogger("hired.routes.score")

router = APIRouter()


@router.post("/score", response_model=ScoreResponse)
async def score(request: ScoreRequest) -> ScoreResponse:
    """Extract a structured profile, score it deterministically, generate lessons."""
    claude = get_claude_service()

    # 1. Claude extracts structured facts (skills, quantified count, exp, edu, clarity).
    try:
        profile = await claude.extract_profile(request.resume, request.target)
    except Exception as exc:
        logger.exception("extraction failed")
        raise HTTPException(status_code=502, detail=f"Profile extraction failed: {exc}")

    # 2. Pure-Python deterministic score + per-category breakdown (no LLM).
    signals = profile_to_signals(profile)
    result = compute_score(signals)
    payload = result.to_payload()  # {score, categories: {label: {score, weight, contribution}}}

    # 3. Claude writes 1-3 micro-lessons for the weakest categories.
    #    Pass human-labeled label->score so lesson.category matches the bars.
    label_scores = {label: cat["score"] for label, cat in payload["categories"].items()}
    try:
        lessons = await claude.generate_lessons(
            resume=request.resume,
            target=request.target,
            categories=label_scores,
            profile=profile,
        )
    except Exception:
        # Lessons are valuable but not worth failing the whole score response over.
        logger.exception("lesson generation failed; returning score without lessons")
        lessons = []

    return ScoreResponse(
        score=payload["score"],
        categories=payload["categories"],
        lessons=lessons,
    )
