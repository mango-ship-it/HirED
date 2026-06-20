"""POST /narrate (TTS) and POST /transcribe (STT) — Deepgram.

/narrate returns an audio_url the frontend plays via <audio> (auto-advance on
onEnded). /transcribe accepts an uploaded audio file and returns the transcript,
which the frontend can feed straight into /score as the `resume` text.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import NarrateRequest, NarrateResponse, TranscribeResponse
from app.services.deepgram_service import get_deepgram_service

logger = logging.getLogger("hired.routes.voice")

router = APIRouter()

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
