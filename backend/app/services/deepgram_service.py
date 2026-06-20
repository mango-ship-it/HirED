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
import logging
import uuid
from pathlib import Path

from deepgram import DeepgramClient

from app.config import get_settings

logger = logging.getLogger("hired.deepgram")

# Where narration MP3s are written; served as static files by FastAPI.
AUDIO_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "audio"
_TTS_MODEL = "aura-2-asteria-en"  # Aura 2 voice
_STT_MODEL = "nova-3"


class DeepgramService:
    """Thin wrapper over the Deepgram client for HirED's voice features."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.deepgram_api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set. Add it to backend/.env.")
        self._client = DeepgramClient(api_key=settings.deepgram_api_key)
        self._public_base_url = settings.public_base_url.rstrip("/")
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    async def narrate(self, text: str) -> str:
        """Synthesize `text` to an MP3 and return its public URL.

        The file is written under static/audio/<uuid>.mp3 and served by FastAPI's
        StaticFiles mount at /static/audio/...
        """
        filename = f"{uuid.uuid4().hex}.mp3"
        out_path = AUDIO_DIR / filename

        def _synthesize() -> None:
            response = self._client.speak.v1.audio.generate(
                text=text,
                model=_TTS_MODEL,
                encoding="mp3",  # match the .mp3 file we write + serve
            )
            out_path.write_bytes(response.stream.getvalue())

        await asyncio.to_thread(_synthesize)
        return f"{self._public_base_url}/static/audio/{filename}"

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
