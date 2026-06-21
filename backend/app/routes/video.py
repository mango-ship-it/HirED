"""POST /video — submit a Pika "your journey" video; GET /video/{prompt_hash} — poll for it.

Async by design (video gen takes ~1-2 min): POST returns a `prompt_hash` + status
'generating'; the frontend polls GET until status='ready' with a `video_url`, then plays
`<video src={video_url}>`. Cached in Redis so the same video is never billed twice.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.errors import ErrorCode, error_response
from app.services.pika_video import build_video_prompt, has_fal, start_video, video_status
from app.services.store import load_profile

router = APIRouter()


@router.post("/video")
async def create_video(body: dict):
    if not has_fal():
        return {"status": "unconfigured", "note": "FAL_KEY not set — video generation disabled."}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        role = (body.get("role") or body.get("target") or "").strip()
        skills = body.get("skills") or []
        if not role and body.get("user_id"):
            record = await load_profile(body["user_id"])
            if record:
                role = (record.get("target") or {}).get("value") or ""
                skills = record.get("missing_skills") or []
        if not role:
            return error_response(
                "Provide a `prompt`, a `role`/`target`, or a `user_id` with a scored profile.",
                ErrorCode.INVALID_INPUT,
                400,
            )
        prompt = build_video_prompt(role, skills)
    return await start_video(prompt)


@router.get("/video/{prompt_hash}")
async def get_video(prompt_hash: str):
    """Poll a submitted video job. Returns {status, video_url?} — 'ready' when done."""
    return await video_status(prompt_hash)
