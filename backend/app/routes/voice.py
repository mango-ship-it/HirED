"""POST /narrate (TTS) and POST /transcribe (STT) — Deepgram.

/narrate returns an audio_url the frontend plays via <audio> (auto-advance on
onEnded). /transcribe accepts an uploaded audio file and returns the transcript,
which the frontend can feed straight into /score as the `resume` text.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import get_settings
from app.models.schemas import NarrateRequest, NarrateResponse, TranscribeResponse
from app.services.deepgram_service import get_deepgram_service
from app.services.store import load_profile

logger = logging.getLogger("hired.routes.voice")

router = APIRouter()


def _profile_text(record: dict) -> str:
    """Flatten a stored profile into text for Deepgram Text Intelligence."""
    parts: list[str] = []
    target = record.get("target") or {}
    if target.get("value"):
        parts.append(f"Career target: {target['value']}.")
    if record.get("matched_skills"):
        parts.append("Skills the candidate has: " + ", ".join(record["matched_skills"]) + ".")
    if record.get("missing_skills"):
        parts.append("Skills the candidate is missing: " + ", ".join(record["missing_skills"]) + ".")
    summary = (record.get("profile") or {}).get("target_summary")
    if summary:
        parts.append(summary)
    return " ".join(parts)

# Guardrail: reject absurd uploads before sending to Deepgram (25 MB).
_MAX_AUDIO_BYTES = 25 * 1024 * 1024


@router.post("/narrate", response_model=NarrateResponse)
async def narrate(request: NarrateRequest) -> NarrateResponse:
    """Synthesize lesson text to speech (Deepgram Aura); return the audio URL."""
    try:
        deepgram = get_deepgram_service()
        audio_url = await deepgram.narrate(request.text)
    except Exception as exc:
        logger.exception("narration failed")
        raise HTTPException(status_code=502, detail=f"Narration failed: {exc}")
    return NarrateResponse(audio_url=audio_url)


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(audio: UploadFile = File(...)) -> TranscribeResponse:
    """Transcribe an uploaded audio file (Deepgram Nova); return the transcript."""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload.")
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 25 MB).")

    try:
        deepgram = get_deepgram_service()
        text = await deepgram.transcribe(audio_bytes)
    except Exception as exc:
        logger.exception("transcription failed")
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}")
    return TranscribeResponse(text=text)


@router.post("/intelligence")
async def intelligence(body: dict):
    """Deepgram Text Intelligence over the user's data (resume + JD + roadmap summary):
    returns summary + topics + intents + sentiment for the frontend to visualize.

    Send `text` (recommended: resume + JD + roadmap), or a `user_id` with a scored
    profile. `custom_topics`/`custom_intents` override the career-domain defaults.
    """
    text = (body.get("text") or "").strip()
    user_id = body.get("user_id")
    if not text and user_id:
        record = await load_profile(user_id)
        if record:
            text = _profile_text(record)
    if not text:
        raise HTTPException(status_code=400, detail="Provide `text` or a `user_id` with a scored profile.")
    if not get_settings().deepgram_api_key:
        return {"configured": False, "note": "DEEPGRAM_API_KEY not set — add it to enable text intelligence."}
    try:
        result = await get_deepgram_service().analyze_text(
            text,
            custom_topics=body.get("custom_topics"),
            custom_intents=body.get("custom_intents"),
        )
    except Exception as exc:
        logger.exception("text intelligence failed")
        raise HTTPException(status_code=502, detail=f"Text intelligence failed: {exc}")
    result["configured"] = True
    return result
