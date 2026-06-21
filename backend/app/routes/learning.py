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
from app.services.exa_search import exa_resources_by_skill, full_roadmap, has_exa, to_steps
from app.services.jd_skills import top_skills_from_jobs
from app.services.jobs import load_jobs
from app.services.leetcode_company import detect_company, fetch_company_problems
from app.services.learning_plan import build_plan, is_coding_role
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

    # Coding role at a known company -> surface that company's real LeetCode problems.
    company = (body.get("company") or "").strip() or None
    leetcode_problems = None
    if is_coding_role(target, skills):
        if not company and target:
            company = await detect_company(target)
        if company:
            leetcode_problems = await fetch_company_problems(
                company, period=(body.get("period") or "thirty-days"), limit=10
            )

    # Real resources via Exa (the core data source) — replace search links per skill.
    # Falls back to the deterministic search links when Exa is unconfigured/capped/empty.
    resources_by_skill = await exa_resources_by_skill(skills, target) if has_exa() else None

    return build_plan(
        skills,
        role=target,
        location=location,
        company=company,
        leetcode_problems=leetcode_problems,
        resources_by_skill=resources_by_skill,
    )


@router.post("/roadmap")
async def roadmap(body: dict):
    """Full Exa-powered roadmap: per-skill courses/practice + events, networking,
    certifications, and scholarships — dynamically queried for this role + missing skills."""
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
        skills = [r["skill"] for r in top_skills_from_jobs(jobs or [], limit=4)]
    if not target and not skills:
        return error_response(
            "Provide a `target` and/or `skills` (or a `user_id` with a scored profile).",
            ErrorCode.INVALID_INPUT,
            400,
        )

    data = await full_roadmap(target, skills, location)
    if data is None:
        return {
            "exa": False,
            "role": target,
            "steps": [],
            "note": "Exa not configured (set EXA_API_KEY) — use /learning-plan for the search-link roadmap.",
        }
    data["exa"] = True
    data["steps"] = to_steps(data)  # ordered, reveal-friendly "unlock as you go" list
    return data


@router.get("/leetcode/{company}")
async def leetcode(company: str, period: str = "thirty-days", limit: int = 15):
    """Top LeetCode problems a company asks (most-frequent first), from the public dataset."""
    problems = await fetch_company_problems(company, period=period, limit=limit)
    if problems is None:
        return {
            "company": company,
            "period": period,
            "count": 0,
            "problems": [],
            "note": "No company-wise list found — check the company name (e.g. 'google', 'goldman sachs').",
        }
    return {"company": company, "period": period, "count": len(problems), "problems": problems}
