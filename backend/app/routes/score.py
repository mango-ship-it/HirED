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

from fastapi import APIRouter, File, Form, UploadFile

from app.errors import ErrorCode, error_response
from app.models.schemas import (
    CategoryBreakdown,
    ScoreResponse,
    ScoreStatus,
    Target,
)
from app.scoring import compute_score
from app.services.claude_service import get_claude_service
from app.services.document_parser import (
    DocumentParseError,
    UnsupportedDocumentError,
    extract_text,
)
from app.services.profile_signals import profile_to_signals

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

    # 3. Claude extracts structured facts; pure code computes the deterministic score.
    claude = get_claude_service()
    try:
        profile = await claude.extract_profile(resume, target_obj.value)
    except Exception as exc:
        logger.exception("extraction failed")
        return error_response(f"Profile extraction failed: {exc}", ErrorCode.SERVER_ERROR, 502)

    result = compute_score(profile_to_signals(profile))
    categories = {
        category.key: CategoryBreakdown(score=category.score, weight=category.weight)
        for category in result.categories.values()
    }

    # 4. Lessons for the weakest categories — valuable, but not worth failing the score over.
    key_scores = {category.key: category.score for category in result.categories.values()}
    try:
        lessons = await claude.generate_lessons(
            resume=resume,
            target=target_obj.value,
            categories=key_scores,
            profile=profile,
        )
    except Exception:
        logger.exception("lesson generation failed; returning score without lessons")
        lessons = []

    # benchmark/resources are fetched from their own endpoints -> still "pending" here.
    return ScoreResponse(
        score=result.score,
        categories=categories,
        lessons=lessons,
        matched_skills=list(profile.matched_skills),
        missing_skills=list(profile.missing_skills),
        status=ScoreStatus(scoring="complete", benchmark="pending", resources="pending"),
    )
