"""POST /narrate (TTS) and POST /transcribe (STT) — Deepgram.

/narrate returns an audio_url the frontend plays via <audio> (auto-advance on
onEnded). /transcribe accepts an uploaded audio file and returns the transcript,
which the frontend can feed straight into /score as the `resume` text.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import get_settings
from app.errors import ErrorCode, error_response
from app.models.schemas import NarrateRequest, NarrateResponse, TranscribeResponse
from app.services.deepgram_service import get_deepgram_service
from app.services.store import load_profile
from app.services.voice_memory import append_turn, get_turns, summarize_for_prompt

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

# Conversation discipline — the fix for "blabbers on load / too fast / talks over me".
_VOICE_RULES = (
    " HOW TO TALK (important): Open with ONLY your greeting, then STOP and wait — do NOT launch "
    "into advice unprompted. Wait until the user has clearly FINISHED their question before you "
    "answer; never talk over them. Keep every reply SHORT — one to three sentences — then stop and "
    "let them speak. Never monologue or list more than two things at once. If a question is broad, "
    "ask one quick clarifying question instead of a long answer. Speak warmly, plainly, and unhurried."
)


def _agent_prompt(record: dict | None, memory_recap: str = "") -> str:
    # Treat a profile with no usable score like no record at all — otherwise the coach
    # would claim "Readiness score: None/100" with em-dash skills for a score-less profile.
    memory_block = f"\n\n{memory_recap}" if memory_recap else ""
    if not record or record.get("score") is None:
        return (
            "You are HirED's warm, encouraging career coach. Help the user understand their job "
            "readiness and how to close their gaps with free resources." + _VOICE_RULES + memory_block
        )
    target = (record.get("target") or {}).get("value") or "their target role"
    resume = (record.get("resume_text") or "").strip()[:1200]
    lessons = record.get("lessons") or []
    cats = record.get("categories") or {}
    breakdown = ", ".join(
        f"{key.replace('_', ' ')} {val.get('score')}/100"
        for key, val in cats.items()
        if isinstance(val, dict) and val.get("score") is not None
    )
    gaps = "\n".join(
        f"    - {(lesson.get('category') or '').replace('_', ' ')}: "
        f"{lesson.get('action') or lesson.get('principle') or ''}"
        for lesson in lessons[:3]
        if isinstance(lesson, dict)
    )
    return (
        "You are HirED's warm, encouraging career coach talking with a job seeker by voice. "
        "You have READ THEIR RESUME and the results on their screen — use these specifics so it's "
        "clear you know them personally, and reference their actual experience by name:\n"
        f"- Target role: {target}\n"
        f"- Readiness score: {record.get('score')}/100\n"
        + (f"- Score breakdown on their screen: {breakdown}\n" if breakdown else "")
        + f"- Skills they already have: {', '.join(record.get('matched_skills') or []) or '—'}\n"
        f"- Skills they still need: {', '.join(record.get('missing_skills') or []) or '—'}\n"
        + (f'- Their resume, in their own words:\n"""\n{resume}\n"""\n' if resume else "")
        + (f"- The top gaps to coach them through:\n{gaps}\n" if gaps else "")
        + "Help them understand the score, prioritize the gap that matters most, and suggest one "
        "concrete free next step at a time. Never shame them."
        + _VOICE_RULES + memory_block
    )


def _agent_greeting(record: dict | None, *, returning: bool = False) -> str:
    target = (record.get("target") or {}).get("value") if record else None
    if returning and target:
        return f"Welcome back! Want to pick up where we left off on {target}?"
    if target:
        return f"Hi, I'm your HirED coach for {target}. What's on your mind?"
    return "Hi, I'm your HirED coach. What would you like to work on?"


def _agent_settings(prompt: str, greeting: str) -> dict:
    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": 16000},
            "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"},
        },
        "agent": {
            "language": "en",
            # endpointing: wait ~600ms of silence before the user's turn ends, so it lets them
            # finish instead of talking over them. speed 0.9: slower, calmer TTS.
            "listen": {"provider": {"type": "deepgram", "model": "nova-3", "endpointing": 600}},
            "think": {"provider": {"type": "open_ai", "model": "gpt-4o-mini"}, "prompt": prompt},
            "speak": {"provider": {"type": "deepgram", "model": _AGENT_VOICE, "speed": 0.9}},
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
    user_id = body.get("user_id") or ""
    record = await load_profile(user_id) if user_id else None
    # Agent memory: fold the user's recent conversation into the prompt so the coach
    # remembers across sessions ("last time you asked about CDL — did you start that course?").
    turns = await get_turns(user_id) if user_id else []
    prompt = _agent_prompt(record, summarize_for_prompt(turns))
    greeting = _agent_greeting(record, returning=bool(turns))
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
        "remembered_turns": len(turns),
    }


@router.post("/voice-agent/memory")
async def voice_agent_memory_append(body: dict):
    """Persist one conversation turn so the coach remembers it next session (agent memory).

    The frontend captures each Deepgram Voice Agent turn (ConversationText events) and POSTs
    `{user_id, role: "user"|"assistant", content}` here. Stored in Redis per user.
    """
    user_id = (body.get("user_id") or "").strip()
    content = (body.get("content") or "").strip()
    if not user_id or not content:
        return error_response("`user_id` and `content` are required.", ErrorCode.INVALID_INPUT, 400)
    count = await append_turn(user_id, body.get("role") or "user", content)
    return {"user_id": user_id, "saved": True, "turns": count}


@router.get("/voice-agent/memory/{user_id}")
async def voice_agent_memory_get(user_id: str):
    """The user's remembered conversation turns (oldest first) — for showing history."""
    turns = await get_turns(user_id)
    return {"user_id": user_id, "turns": turns, "count": len(turns)}
