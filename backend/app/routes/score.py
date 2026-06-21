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

import hashlib
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, UploadFile

from app.errors import ErrorCode, error_response
from app.models.schemas import (
    Annotation,
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
from app.services.jd_context import build_lesson_context
from app.services.jd_skills import jd_enriched_skills
from app.services.jobs import load_jobs
from app.services.profile_vectors import add_profile
from app.services.resume_guard import has_usable_resume
from app.services import score_cache
from app.services.scoring_engine import get_scorer
from app.services.store import get_store, save_profile

logger = logging.getLogger("hired.routes.score")

router = APIRouter()

_MAX_RESUME_BYTES = 10 * 1024 * 1024  # 10 MB
_SCORE_TTL = 7 * 24 * 3600  # cache an identical (resume, target) score for a week


def _locate(text: str, quote: str) -> tuple[int, int]:
    """Char offsets of `quote` in `text` so the frontend highlights the FULL span exactly
    (no fragile client-side matching). Falls back to whitespace-tolerant matching for file
    uploads where newlines/spacing differ from what Claude quoted. (-1, -1) if not found."""
    q = (quote or "").strip()
    if not q:
        return -1, -1
    idx = text.find(q)
    if idx >= 0:
        return idx, idx + len(q)
    tokens = [re.escape(tok) for tok in q.split()]
    if tokens:
        match = re.search(r"\s+".join(tokens), text)
        if match:
            return match.start(), match.end()
    return -1, -1


def _category_explanations(profile) -> dict[str, str]:
    """Short, deterministic 'why it scored that' note per category (results page 2)."""
    matched = len(profile.matched_skills)
    required = len(profile.required_skills) or (matched + len(profile.missing_skills))
    gaps = ", ".join(profile.missing_skills[:3])
    return {
        "skills_match": (
            f"You show {matched} of ~{required} skills this role looks for"
            + (f"; key gaps: {gaps}." if gaps else ".")
        ),
        "quantified_achievements": (
            f"{profile.quantified_achievement_count} of "
            f"{profile.total_achievement_count or 'your'} bullets use concrete numbers or impact."
        ),
        "experience": (
            f"Your resume reflects about {profile.years_experience:g} year(s) of relevant experience."
        ),
        "education": "Detected education: " + {
            "none": "no degree listed", "some": "some college", "certificate": "a certificate",
            "associate": "an associate degree", "bachelor": "a bachelor's degree",
            "master": "a master's degree", "doctorate": "a doctorate",
        }.get(profile.education_level, profile.education_level) + ".",
        "clarity": "Reflects how clearly your resume reads — action verbs, structure, and concision.",
    }


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

    # Content floor: a near-empty input (a stray page number, a lone ".", a one-word
    # transcript, a scanned PDF that yielded a single glyph) must NOT be scored as a real
    # resume — that produces a misleading low-but-non-zero number with empty highlights.
    # Reject it honestly BEFORE the cache so a fake score is never cached or re-served.
    if not has_usable_resume(resume):
        return error_response(
            "We couldn't find enough resume text to score. Paste your experience, skills, "
            "and education, or upload a readable .pdf/.docx file.",
            ErrorCode.INVALID_INPUT,
            400,
        )

    # 3. Load cached JD postings UP FRONT so the score cache key reflects them — a later
    #    /jobs/refresh changes the key and forces a re-score (never serves stale skills).
    try:
        cached_jobs = await load_jobs(target_obj.value)
    except Exception:
        cached_jobs = None

    # Consistency: identical (resume, target, JD-state) -> identical score, served from cache,
    # so the same input never yields a different number (Claude extraction can vary per run).
    cache_key = "score:v2:" + hashlib.sha256(
        f"{resume}\n{target_obj.value}\n{len(cached_jobs or [])}".encode()
    ).hexdigest()[:24]
    try:
        cached = await get_store().get_json(cache_key)
    except Exception:
        cached = None
    if cached is not None:
        return ScoreResponse.model_validate(cached)

    # Semantic cache fallback — catches near-identical resumes (PDF re-parse artifacts,
    # whitespace) that missed the exact cache. Threshold 0.04 absorbs only trivial changes;
    # meaningful edits always produce a fresh score.
    semantic_key = f"{resume[:1500]}\n---TARGET---\n{target_obj.value}\n---JDS---\n{len(cached_jobs or [])}"
    sem_cached = await score_cache.get_cached(semantic_key)
    if sem_cached is not None:
        sem_cached["resume_text"] = resume
        for ann in sem_cached.get("annotations", []):
            start, end = _locate(resume, ann.get("quote", ""))
            ann["start"] = start
            ann["end"] = end
        return ScoreResponse.model_validate(sem_cached)

    profile = await extract_profile(resume, target_obj.value)

    # Accuracy bridge: enrich skills against the REAL postings + build a grounded lesson
    # digest. Additive + graceful — falls back to extracted skills when no jobs are cached.
    jd_context = ""
    if cached_jobs:
        try:
            required, matched, missing = jd_enriched_skills(resume, cached_jobs)
            if required:
                profile = profile.model_copy(
                    update={
                        "required_skills": required,
                        "matched_skills": matched,
                        "missing_skills": missing,
                    }
                )
            jd_context = build_lesson_context(cached_jobs, profile.missing_skills)
        except Exception:
            logger.exception("JD-skill enrichment failed; using extracted skills")

    outcome = await get_scorer().score(profile=profile, resume=resume, target=target_obj.value)
    explanations = _category_explanations(profile)
    categories = {
        key: CategoryBreakdown(
            score=cat.score, weight=cat.weight, explanation=explanations.get(key, "")
        )
        for key, cat in outcome.categories.items()
    }

    # 4. Lessons for the weakest categories (Claude if keyed, else templated fallback).
    key_scores = {key: cat.score for key, cat in outcome.categories.items()}
    lessons = await generate_lessons(
        resume=resume,
        target=target_obj.value,
        category_scores=key_scores,
        profile=profile,
        jd_context=jd_context,
    )

    # Resume highlight annotations (Claude path only; empty on the heuristic path). Built
    # defensively so a malformed item never breaks the score.
    annotations = []
    for a in profile.annotations:
        if isinstance(a, dict) and a.get("quote"):
            start, end = _locate(resume, a["quote"])
            annotations.append(
                Annotation(
                    quote=a.get("quote", ""),
                    category=a.get("category", ""),
                    sentiment=a.get("sentiment", ""),
                    reason=a.get("reason", ""),
                    start=start,
                    end=end,
                )
            )

    # Remember this user's FULL scored result so the frontend can re-render the breakdown
    # page — including the resume text + its highlights — via GET /profile/{user_id},
    # WITHOUT ever asking the user to upload their resume again. Best-effort; never fails.
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
                "resume_text": resume,
                "has_resume": True,  # passed the content floor above
                "annotations": [a.model_dump() for a in annotations],
                "categories": {k: v.model_dump() for k, v in categories.items()},
                "lessons": [lesson.model_dump() for lesson in lessons],
                "saved_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        logger.exception("failed to save profile for %s", user_id)

    # Index this learner into the 'people like you' vector cohort (best-effort, non-blocking).
    try:
        await add_profile(user_id, target_obj.value, outcome.score, ", ".join(profile.missing_skills[:6]))
    except Exception:
        logger.exception("profile vector indexing failed for %s", user_id)

    # benchmark/resources are fetched from their own endpoints -> still "pending" here.
    response = ScoreResponse(
        score=outcome.score,
        categories=categories,
        lessons=lessons,
        matched_skills=list(profile.matched_skills),
        missing_skills=list(profile.missing_skills),
        resume_text=resume,  # full text so the frontend can render + highlight against it
        has_resume=True,  # /score only reaches here with a usable resume (floor above)
        annotations=annotations,
        status=ScoreStatus(scoring="complete", benchmark="pending", resources="pending"),
    )
    try:
        await get_store().set_json(cache_key, response.model_dump(), ttl=_SCORE_TTL)
    except Exception:
        pass
    try:
        await score_cache.set_cached(semantic_key, response.model_dump())
    except Exception:
        pass
    return response
