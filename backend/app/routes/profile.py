"""GET /profile/{user_id} — recall a user's saved profile/skills.

Populated by /score (it stores the parsed profile per user_id). Lets the frontend
show "we remember you" / pre-fill, and powers re-score from a known user.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.errors import ErrorCode, error_response
from app.services.store import get_store, load_profile

router = APIRouter()


@router.get("/profile/{user_id}")
async def get_profile(user_id: str):
    record = await load_profile(user_id)
    if record is None:
        return error_response("No saved profile for this user.", ErrorCode.NOT_FOUND, 404)
    # Normalize the shape so OLD records (saved before resume_text/annotations existed,
    # where the keys are absent — not "") look identical to new ones. The frontend always
    # gets resume_text + an explicit has_resume to gate the side-by-side resume panel on,
    # instead of inferring from a possibly-missing key. Immutable: build a new dict.
    resume_text = record.get("resume_text") or ""
    return {
        **record,
        "resume_text": resume_text,
        "annotations": record.get("annotations") or [],
        "has_resume": bool(resume_text.strip()),
    }


@router.post("/progress")
async def save_progress(body: dict):
    """Persist a user's roadmap progress (unlocked/completed steps) in Redis.

    The frontend owns the shape — send `progress` as any JSON (e.g.
    {unlocked:[1,2], done:[1], target:"Bus Driver"}). Stored per user_id and survives
    restarts via Redis. This is why we DON'T need SQLite: Redis is already our durable
    per-user store.
    """
    user_id = (body.get("user_id") or "").strip()
    if not user_id:
        return error_response("`user_id` is required.", ErrorCode.INVALID_INPUT, 400)
    if "progress" not in body:
        return error_response("`progress` is required.", ErrorCode.INVALID_INPUT, 400)
    await get_store().set_json(f"progress:{user_id}", body["progress"], ttl=None)  # permanent
    return {"user_id": user_id, "saved": True}


@router.get("/progress/{user_id}")
async def get_progress(user_id: str):
    """Load a user's saved roadmap progress (empty object if none yet)."""
    data = await get_store().get_json(f"progress:{user_id}")
    return {"user_id": user_id, "progress": data or {}}
