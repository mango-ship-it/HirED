"""Pika video generation via fal.ai — async submit + poll, Redis-cached.

Generates a short cinematic "your journey" video for the user's target role. Video gen is
slow (~1-2 min) and costs money, so this is ASYNC: `start_video` submits a job and returns a
`prompt_hash`; the frontend polls `video_status(prompt_hash)` until status='ready' with a
`video_url`. Cached in Redis by prompt so the same video is never generated (or billed) twice.

Graceful: no FAL_KEY -> {status:'unconfigured'} (frontend hides the video). Verified async
API against fal-client (submit_async -> request_id; status_async -> Completed; result_async).
"""

from __future__ import annotations

import hashlib
import logging
import os

from app.config import get_settings
from app.services.store import get_store

logger = logging.getLogger("hired.pika")

_MODEL = "fal-ai/pika/v2.2/text-to-video"


def has_fal() -> bool:
    return bool(get_settings().fal_api_key)


def _ensure_key() -> None:
    key = get_settings().fal_api_key
    if key and os.environ.get("FAL_KEY") != key:
        os.environ["FAL_KEY"] = key  # fal_client reads FAL_KEY from the env


def build_video_prompt(role: str, skills: list[str] | None = None) -> str:
    learn = (", learning " + " and ".join(skills[:2])) if skills else ""
    return (
        f"A short cinematic, uplifting animation following a determined person's journey to "
        f"becoming a {role or 'their dream job'}{learn}, then succeeding at work and helping "
        f"others. Warm hopeful tone, soft golden lighting, inspiring, smooth camera movement."
    )


async def start_video(prompt: str) -> dict:
    """Submit a Pika job (or return the cached / already-in-flight one)."""
    if not has_fal():
        return {"status": "unconfigured"}
    digest = hashlib.sha1(prompt.encode()).hexdigest()[:16]
    key = f"video:{digest}"
    try:
        cached = await get_store().get_json(key)
    except Exception:
        cached = None
    if cached:
        return {"prompt_hash": digest, **cached}
    _ensure_key()
    try:
        import fal_client

        handle = await fal_client.submit_async(
            _MODEL,
            arguments={"prompt": prompt, "aspect_ratio": "16:9", "resolution": "720p", "duration": 5},
        )
        record = {"status": "generating", "request_id": handle.request_id}
    except Exception as exc:
        logger.warning("fal submit failed: %s", exc)
        return {"prompt_hash": digest, "status": "error", "detail": str(exc)[:200]}
    await get_store().set_json(key, record, ttl=None)
    return {"prompt_hash": digest, **record}


async def video_status(prompt_hash: str) -> dict:
    """Poll a submitted Pika job; cache + return the URL once ready."""
    if not has_fal():
        return {"status": "unconfigured"}
    key = f"video:{prompt_hash}"
    try:
        record = await get_store().get_json(key)
    except Exception:
        record = None
    if not record:
        return {"status": "unknown"}
    if record.get("status") == "ready":
        return {"prompt_hash": prompt_hash, **record}
    request_id = record.get("request_id")
    if not request_id:
        return {"prompt_hash": prompt_hash, "status": record.get("status", "generating")}
    _ensure_key()
    try:
        import fal_client

        status = await fal_client.status_async(_MODEL, request_id)
        if isinstance(status, fal_client.Completed):
            result = await fal_client.result_async(_MODEL, request_id)
            url = ((result or {}).get("video") or {}).get("url")
            ready = {"status": "ready", "video_url": url}
            await get_store().set_json(key, ready, ttl=None)
            return {"prompt_hash": prompt_hash, **ready}
    except Exception as exc:
        logger.warning("fal status/result failed: %s", exc)
    return {"prompt_hash": prompt_hash, "status": "generating"}
