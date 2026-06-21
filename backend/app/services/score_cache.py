"""RedisVL SemanticCache for the /score response — prevents numeric score
fluctuation when the same resume is re-submitted with minor textual
differences (PDF re-parse artifacts, whitespace).

Acts as a fallback between the exact SHA-256 cache and a live Claude call.
Threshold 0.04 absorbs only near-verbatim duplicates; meaningful edits
always produce a fresh score.

Keyed on resume[:1500] + "\\n---TARGET---\\n" + target.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from app.config import get_settings
from app.services.embeddings import embed_one, get_model

logger = logging.getLogger("hired.score_cache")

_DISTANCE_THRESHOLD = 0.04
_TTL = 7 * 24 * 3600
_TIMEOUTS = {"socket_connect_timeout": 5, "socket_timeout": 5}

_cache = None
_status = "not_built"
_lock = asyncio.Lock()


async def _get_cache():
    """Lazily build the RedisVL SemanticCache (shared fastembed vectorizer). None if down."""
    global _cache, _status
    if _cache is not None:
        return _cache
    if _status == "failed":
        return None
    async with _lock:
        if _cache is not None or _status == "failed":
            return _cache
        try:
            model = await get_model()
            if model is None:
                _status = "failed"
                return None
            from redisvl.extensions.cache.llm import SemanticCache
            from redisvl.utils.vectorize import CustomVectorizer

            def build():
                vectorizer = CustomVectorizer(
                    embed=lambda t: embed_one(model, t), dtype="float32"
                )
                return SemanticCache(
                    name="hired_score_cache",
                    vectorizer=vectorizer,
                    distance_threshold=_DISTANCE_THRESHOLD,
                    ttl=_TTL,
                    redis_url=get_settings().redis_url,
                    connection_kwargs=_TIMEOUTS,
                )

            _cache = await asyncio.to_thread(build)
            _status = "ready"
            logger.info("score semantic cache ready (threshold=%.2f)", _DISTANCE_THRESHOLD)
        except Exception as exc:
            _status = "failed"
            logger.info(
                "score semantic cache unavailable (%s) — exact cache still applies", exc
            )
            return None
    return _cache


def status() -> str:
    return _status


async def get_cached(key: str) -> Optional[dict]:
    """Return the cached ScoreResponse dict for a semantically-similar key, else None."""
    cache = await _get_cache()
    if cache is None:
        return None
    try:
        hits = await asyncio.to_thread(lambda: cache.check(prompt=key, num_results=1))
        if hits:
            return json.loads(hits[0]["response"])
    except Exception as exc:
        logger.debug("score semantic cache check failed (%s)", exc)
    return None


async def set_cached(key: str, payload: dict) -> None:
    """Store key -> ScoreResponse dict for future semantic hits. Best-effort; never raises."""
    cache = await _get_cache()
    if cache is None:
        return
    try:
        await asyncio.to_thread(
            lambda: cache.store(prompt=key, response=json.dumps(payload))
        )
    except Exception as exc:
        logger.debug("score semantic cache store failed (%s)", exc)
