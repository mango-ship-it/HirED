"""POST /jobs/refresh + GET /jobs/{target} — pull real jobs (JobSpy), remember in Redis.

`/jobs/refresh` scrapes the boards (slow, 10-30s, best-effort) and stores the result
in Redis keyed by target. `GET /jobs/{target}` reads it back instantly. This is the
"pull + remember job data" system; it is NOT wired into scoring yet.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.errors import ErrorCode, error_response
from app.services.jd_skills import compare_to_market
from app.services.jobs import DEFAULT_SITES, fetch_and_store_jobs, load_jobs
from app.services.store import load_profile

router = APIRouter()


@router.post("/jobs/refresh")
async def refresh_jobs(body: dict):
    target = (body.get("target") or "").strip()
    if not target:
        return error_response("`target` is required.", ErrorCode.INVALID_INPUT, 400)
    jobs = await fetch_and_store_jobs(
        target,
        location=(body.get("location") or "United States").strip(),
        sites=body.get("sites") or DEFAULT_SITES,
        results=int(body.get("results") or 15),
    )
    return {"target": target, "count": len(jobs), "stored": bool(jobs), "jobs": jobs}


@router.get("/jobs/{target}")
async def get_jobs(target: str):
    jobs = await load_jobs(target)
    return {"target": target, "count": len(jobs or []), "jobs": jobs or []}


@router.get("/jobs/{target}/skills")
async def jobs_skills(target: str, user_id: str | None = None):
    """Real in-demand skills for a role (from cached JD postings) vs the user's skills.

    Reinforces readiness with real market data: "N postings want X; you have/lack it."
    Pass ?user_id=... to compare against that user's stored profile.
    """
    jobs = await load_jobs(target)
    if not jobs:
        return {
            "target": target,
            "sample_size": 0,
            "market_skills": [],
            "note": "No jobs cached for this target — call POST /jobs/refresh first.",
        }
    candidate_skills: list[str] = []
    if user_id:
        record = await load_profile(user_id)
        if record:
            candidate_skills = list(record.get("matched_skills") or [])
    result = compare_to_market(jobs, candidate_skills)
    result["target"] = target
    return result
