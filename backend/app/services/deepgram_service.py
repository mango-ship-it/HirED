"""Deepgram integration — TTS (Aura) for lesson narration + STT (Nova) for voice.

Verified against deepgram-sdk==7.3.1 (the v-namespaced client API):
  client = DeepgramClient(api_key=...)
  # TTS:
  resp = client.speak.v1.audio.generate(text=..., model="aura-2-asteria-en")
  audio_bytes = resp.stream.getvalue()
  # STT:
  resp = client.listen.v1.media.transcribe_file(request=<bytes>, model="nova-3",
                                                 smart_format=True)
  transcript = resp.results.channels[0].alternatives[0].transcript

The SDK calls are synchronous/blocking, so we run them in a thread via
asyncio.to_thread to avoid blocking the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from deepgram import DeepgramClient

from app.config import get_settings

logger = logging.getLogger("hired.deepgram")

# Where narration MP3s are written; served as static files by FastAPI.
AUDIO_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "audio"
_TTS_MODEL = "aura-2-asteria-en"  # Aura 2 voice
_STT_MODEL = "nova-3"

# Career-domain custom topics/intents for Text Intelligence — passed to the API (NOT
# hardcoded in the playground), and overridable per request so the frontend stays flexible.
_CAREER_TOPICS = [
    "career goals", "technical skills", "soft skills", "work experience",
    "education", "certifications", "leadership", "skill gaps",
]
_CAREER_INTENTS = [
    "find a job", "learn a new skill", "get certified", "switch careers",
    "build experience", "network with people", "improve resume",
]


def _parse_intelligence(resp) -> dict:
    """Defensively pull summary/topics/intents/sentiment out of a Deepgram read response."""
    try:
        data = resp.model_dump() if hasattr(resp, "model_dump") else (
            resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
        )
    except Exception:
        data = {}
    results = data.get("results") or {}

    def _flatten(section: str, key: str) -> list[str]:
        out: list[str] = []
        for seg in (results.get(section) or {}).get("segments") or []:
            for item in seg.get(section) or seg.get(key + "s") or []:
                val = item.get(key) if isinstance(item, dict) else None
                if val and val not in out:
                    out.append(val)
        return out

    avg = (results.get("sentiments") or {}).get("average") or {}
    return {
        "summary": ((results.get("summary") or {}).get("text")) or "",
        "topics": _flatten("topics", "topic"),
        "intents": _flatten("intents", "intent"),
        "sentiment": {"label": avg.get("sentiment"), "score": avg.get("sentiment_score")} if avg else {},
    }


class DeepgramService:
    """Thin wrapper over the Deepgram client for HirED's voice features."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.deepgram_api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set. Add it to backend/.env.")
        self._client = DeepgramClient(api_key=settings.deepgram_api_key)
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    async def narrate(self, text: str) -> str:
        """Synthesize `text` to an MP3 and return a RELATIVE url (/static/audio/...).

        Relative on purpose: the frontend prepends its own API base, so the audio works
        through any tunnel (the URL changes per restart) without server config. Cached by
        a hash of (model, text): identical narration is served from the existing file with
        NO Deepgram call — so re-runs and demo practice don't burn credits.
        """
        digest = hashlib.sha256(f"{_TTS_MODEL}\n{text}".encode()).hexdigest()[:16]
        filename = f"{digest}.mp3"
        out_path = AUDIO_DIR / filename
        url = f"/static/audio/{filename}"  # frontend prepends API_BASE

        if out_path.exists():  # cache hit — skip the API call
            return url

        def _synthesize() -> None:
            # generate() returns Iterator[bytes] (streamed audio chunks) — join them.
            response = self._client.speak.v1.audio.generate(
                text=text,
                model=_TTS_MODEL,
                encoding="mp3",  # match the .mp3 file we write + serve
            )
            out_path.write_bytes(b"".join(response))

        await asyncio.to_thread(_synthesize)
        return url

    async def analyze_text(
        self, text: str, *, custom_topics: list[str] | None = None,
        custom_intents: list[str] | None = None,
    ) -> dict:
        """Deepgram Text Intelligence: summary + topics + intents + sentiment on the text.

        Runs the /read endpoint with career-domain custom topics/intents (overridable)
        so the frontend gets structured signals to visualize — no hardcoded playground.
        """
        topics = custom_topics or _CAREER_TOPICS
        intents = custom_intents or _CAREER_INTENTS

        def _analyze():
            return self._client.read.v1.text.analyze(
                request={"text": text[:90000]},  # Deepgram read text cap
                language="en",  # required by the /read API
                summarize="v2",
                topics=True,
                intents=True,
                sentiment=True,
                custom_topic=topics,
                custom_topic_mode="extended",
                custom_intent=intents,
                custom_intent_mode="extended",
            )

        resp = await asyncio.to_thread(_analyze)
        return _parse_intelligence(resp)

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe raw audio bytes to text and return the transcript."""

        def _transcribe() -> str:
            response = self._client.listen.v1.media.transcribe_file(
                request=audio_bytes,
                model=_STT_MODEL,
                smart_format=True,
            )
            return response.results.channels[0].alternatives[0].transcript

        return await asyncio.to_thread(_transcribe)


_service: DeepgramService | None = None


def get_deepgram_service() -> DeepgramService:
    global _service
    if _service is None:
        _service = DeepgramService()
    return _service
