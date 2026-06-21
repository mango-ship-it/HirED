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
    # Min-content floor: don't burn a paid Deepgram call on a stray glyph that would just
    # come back empty-but-"configured" (frames nothing as a real analysis).
    if len(text) < 15:
        raise HTTPException(
            status_code=400,
            detail="Not enough text to analyze — provide a fuller `text` or a `user_id` with a scored profile.",
        )
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


_AGENT_VOICE = "aura-2-asteria-en"


def _agent_prompt(record: dict | None) -> str:
    # Treat a profile with no usable score like no record at all — otherwise the coach
    # would claim "Readiness score: None/100" with em-dash skills for a score-less profile.
    if not record or record.get("score") is None:
        return (
            "You are HirED's warm, encouraging career coach. Help the user understand their "
            "job readiness and how to close their gaps with free resources. Keep answers "
            "short and conversational for voice."
        )
    target = (record.get("target") or {}).get("value") or "their target role"
    return (
        "You are HirED's warm, encouraging career coach talking with a job seeker by voice. "
        "Use THEIR data to give specific, personal advice:\n"
        f"- Target role: {target}\n"
        f"- Readiness score: {record.get('score')}/100\n"
        f"- Skills they have: {', '.join(record.get('matched_skills') or []) or '—'}\n"
        f"- Skills they're missing: {', '.join(record.get('missing_skills') or []) or '—'}\n"
        "Help them understand the score, prioritize the gaps that matter most, and suggest "
        "concrete free next steps. Be concise, jargon-free, and never shaming."
    )


def _agent_greeting(record: dict | None) -> str:
    target = (record.get("target") or {}).get("value") if record else None
    if target:
        return (
            f"Hi! I'm your HirED coach. I see you're aiming for {target} — ask me anything "
            "about your score or how to close your gaps."
        )
    return "Hi! I'm your HirED coach. Ask me anything about your readiness and your next steps."


def _agent_settings(prompt: str, greeting: str) -> dict:
    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": 16000},
            "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"},
        },
        "agent": {
            "language": "en",
            "listen": {"provider": {"type": "deepgram", "model": "nova-3"}},
            "think": {"provider": {"type": "open_ai", "model": "gpt-4o-mini"}, "prompt": prompt},
            "speak": {"provider": {"type": "deepgram", "model": _AGENT_VOICE}},
            "greeting": greeting,
        },
    }


@router.post("/voice-agent/config")
async def voice_agent_config(body: dict):
    """Config for a Deepgram Voice Agent that chats about THIS user's results.

    Returns a short-lived `token` (so the browser never holds the raw key) + a `settings`
    object whose system prompt is injected with the user's target/score/gaps. The frontend
    opens the Deepgram Voice Agent WebSocket (`ws_url`) with the token and sends `settings`.
    """
    if not get_settings().deepgram_api_key:
        return {"configured": False, "note": "DEEPGRAM_API_KEY not set — voice agent disabled."}
    record = await load_profile(body["user_id"]) if body.get("user_id") else None
    prompt = _agent_prompt(record)
    greeting = _agent_greeting(record)
    try:
        token = await get_deepgram_service().grant_token(ttl_seconds=120)
    except Exception as exc:
        logger.warning("deepgram token grant failed: %s", exc)
        token = None
    return {
        "configured": True,
        "ws_url": "wss://agent.deepgram.com/v1/agent/converse",
        "token": token,
        "greeting": greeting,
        "settings": _agent_settings(prompt, greeting),
    }
