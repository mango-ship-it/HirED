"""POST /learning-plan — real, domain-agnostic resources for a user's skill gaps.

Body: { target?, location?, skills?: [...], user_id? }
- skills given      -> use them
- else user_id      -> use that user's stored missing_skills
- else target       -> derive from real JobSpy demand (cached jobs for the role)
Returns a per-skill breakdown of real resources (video/course/local/practice) plus
role-level credentials/local options. The frontend renders the cards.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.errors import ErrorCode, error_response
from app.services.jd_skills import top_skills_from_jobs
from app.services.jobs import load_jobs
from app.services.learning_plan import build_plan
from app.services.store import load_profile

router = APIRouter()


@router.post("/learning-plan")
async def learning_plan(body: dict):
    target = (body.get("target") or "").strip()
    location = (body.get("location") or "").strip()
    skills = [s for s in (body.get("skills") or []) if s]
    user_id = body.get("user_id")

    if not skills and user_id:
        record = await load_profile(user_id)
        if record:
            skills = list(record.get("missing_skills") or [])

    if not skills and target:
        jobs = await load_jobs(target)
        skills = [r["skill"] for r in top_skills_from_jobs(jobs or [], limit=6)]

    if not skills:
        return error_response(
            "Provide `skills`, a `user_id` with a scored profile, or a `target` with cached jobs.",
            ErrorCode.INVALID_INPUT,
            400,
        )
    return build_plan(skills, role=target, location=location)
