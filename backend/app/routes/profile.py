"""GET /profile/{user_id} — recall a user's saved profile/skills.

Populated by /score (it stores the parsed profile per user_id). Lets the frontend
show "we remember you" / pre-fill, and powers re-score from a known user.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.errors import ErrorCode, error_response
from app.services.store import load_profile

router = APIRouter()


@router.get("/profile/{user_id}")
async def get_profile(user_id: str):
    record = await load_profile(user_id)
    if record is None:
        return error_response("No saved profile for this user.", ErrorCode.NOT_FOUND, 404)
    return record
