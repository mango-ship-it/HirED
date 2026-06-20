"""POST /score — the first page's backend: take the uploaded resume, parse it,
score it, and return the contract-shaped report.

Per API_CONTRACT.md this is a **multipart upload**:
    user_id      (form)  — client-generated UUID
    target       (form)  — JSON string {type, value}
    resume_file  (file)  — .pdf / .docx        ─┐ exactly one of these
    resume_text  (form)  — pasted plain text   ─┘ (text path supports the "or text" case)

Pipeline: parse file -> plain text (document_parser) -> Claude extracts structured
facts -> pure-Python deterministic score (scoring.py) -> Claude writes 1-3 lessons.
Claude only extracts + teaches; it never invents the number (MASTER.md §7).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, UploadFile

from app.errors import ErrorCode, error_response
from app.models.schemas import (
    CategoryBreakdown,
    ScoreResponse,
    ScoreStatus,
    Target,
)
from app.services.document_parser import (
    DocumentParseError,
    UnsupportedDocumentError,
    extract_text,
)
from app.services.extractor import extract_profile, generate_lessons
from app.services.scoring_engine import get_scorer
from app.services.store import save_profile

logger = logging.getLogger("hired.routes.score")

router = APIRouter()

_MAX_RESUME_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/score")
async def score(
    user_id: str = Form(...),
    target: str = Form(..., description='JSON string: {"type": "...", "value": "..."}'),
    resume_file: UploadFile | None = File(default=None),
    resume_text: str | None = Form(default=None),
):
    """Parse the resume, score it deterministically, and generate lessons."""
    # 1. Parse the target (multipart fields arrive as strings).
    try:
        target_obj = Target.model_validate_json(target)
    except Exception:
        return error_response(
            '`target` must be JSON of the form {"type": "...", "value": "..."}.',
            ErrorCode.INVALID_INPUT,
            400,
        )

    # 2. Resolve the resume to plain text — from the uploaded file, or pasted text.
    if resume_file is not None:
        raw = await resume_file.read()
        if len(raw) > _MAX_RESUME_BYTES:
            return error_response("Resume file too large (max 10 MB).", ErrorCode.INVALID_INPUT, 413)
        try:
            resume = extract_text(
                raw, content_type=resume_file.content_type, filename=resume_file.filename
            )
        except UnsupportedDocumentError as exc:
            return error_response(str(exc), ErrorCode.INVALID_INPUT, 400)
        except DocumentParseError as exc:
            return error_response(str(exc), ErrorCode.PARSE_FAILED, 400)
    elif resume_text and resume_text.strip():
        resume = resume_text.strip()
    else:
        return error_response(
            "Provide a resume_file (.pdf/.docx) or resume_text.",
            ErrorCode.INVALID_INPUT,
            400,
        )

    # 3. Extract structured facts (Claude if ANTHROPIC_API_KEY is set, else heuristic
    #    — so this works with zero config), then SCORE via the pluggable scorer.
    profile = await extract_profile(resume, target_obj.value)
    outcome = await get_scorer().score(profile=profile, resume=resume, target=target_obj.value)
    categories = {
        key: CategoryBreakdown(score=cat.score, weight=cat.weight)
        for key, cat in outcome.categories.items()
    }

    # 4. Lessons for the weakest categories (Claude if keyed, else templated fallback).
    key_scores = {key: cat.score for key, cat in outcome.categories.items()}
    lessons = await generate_lessons(
        resume=resume,
        target=target_obj.value,
        category_scores=key_scores,
        profile=profile,
    )

    # Remember this user's parsed profile/skills so the app can recall their inputs
    # across calls (Redis if available, else in-memory). Best-effort — never fail the
    # score over a store hiccup.
    try:
        await save_profile(
            user_id,
            {
                "user_id": user_id,
                "target": target_obj.model_dump(),
                "score": outcome.score,
                "matched_skills": list(profile.matched_skills),
                "missing_skills": list(profile.missing_skills),
                "profile": profile.model_dump(),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        logger.exception("failed to save profile for %s", user_id)

    # benchmark/resources are fetched from their own endpoints -> still "pending" here.
    return ScoreResponse(
        score=outcome.score,
        categories=categories,
        lessons=lessons,
        matched_skills=list(profile.matched_skills),
        missing_skills=list(profile.missing_skills),
        status=ScoreStatus(scoring="complete", benchmark="pending", resources="pending"),
    )
