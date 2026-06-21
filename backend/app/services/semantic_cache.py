"""RedisVL SemanticCache over the expensive Exa lookups — a NAMED RedisVL AI feature.

Two semantically-similar queries ("free electrician courses" ~= "electrician training
free") reuse ONE cached result, so we don't spend the Exa budget twice on near-duplicate
searches. The threshold is paraphrase-tight so a different role/intent never collides.

Deliberately scoped to the role/query layer — NOT the resume-specific /score response,
which must keep responding to resume edits (a better resume must still raise the score)
and whose annotations quote the exact resume. Embeds with the shared fastembed model.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from app.config import get_settings
from app.services.embeddings import embed_one, get_model

logger = logging.getLogger("hired.semantic_cache")

# Cosine distance (0 = identical). CRITICAL: our queries are TEMPLATED, so the same role/intent
# reworded lands near-identical (~0.03-0.05), while a DIFFERENT role in the same boilerplate
# template (e.g. "...candidates for {Nurse}" vs "{Software Developer}") was measured as low as
# ~0.12 — the long template dominates the embedding. 0.07 captures near-duplicate intents while
# staying well below that cross-role floor, so we NEVER serve another role's cards.
_DISTANCE_THRESHOLD = 0.07
_TTL = 30 * 24 * 3600  # match the Exa exact-cache horizon
_TIMEOUTS = {"socket_connect_timeout": 5, "socket_timeout": 5}  # match store.py for remote Redis/TLS

_cache = None
_status = "not_built"  # not_built | ready | failed
_lock = asyncio.Lock()


async def _get_cache():
    """Lazily build the RedisVL SemanticCache (shared fastembed vectorizer). None if down."""
    global _cache, _status
    if _cache is not None:
        return _cache
    if _status == "failed":
        return None
    async with _lock:  # double-checked: only ONE concurrent first-caller builds the cache
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
                # Bridge our fastembed embedder into RedisVL (no PyTorch). Built INSIDE the
                # thread so the vectorizer's one-shot dims-probe embed runs off the event loop.
                vectorizer = CustomVectorizer(embed=lambda t: embed_one(model, t), dtype="float32")
                return SemanticCache(
                    name="hired_exa_cache",
                    vectorizer=vectorizer,
                    distance_threshold=_DISTANCE_THRESHOLD,
                    ttl=_TTL,
                    redis_url=get_settings().redis_url,
                    connection_kwargs=_TIMEOUTS,
                )

            _cache = await asyncio.to_thread(build)
            _status = "ready"
            logger.info("semantic cache ready (Exa layer, threshold=%.2f)", _DISTANCE_THRESHOLD)
        except Exception as exc:  # no redisvl / no Redis / no search module
            _status = "failed"
            logger.info("semantic cache unavailable (%s) — exact cache still applies", exc)
            return None
    return _cache


def status() -> str:
    return _status


async def get_cached(query: str) -> Optional[Any]:
    """Return the payload stored for a semantically-similar query, else None. Never raises."""
    cache = await _get_cache()
    if cache is None:
        return None
    try:
        hits = await asyncio.to_thread(lambda: cache.check(prompt=query, num_results=1))
        if hits:
            return json.loads(hits[0]["response"])
    except Exception as exc:
        logger.debug("semantic cache check failed (%s)", exc)
    return None


async def set_cached(query: str, payload: Any) -> None:
    """Store query -> payload for future semantic hits. Best-effort; never raises."""
    cache = await _get_cache()
    if cache is None:
        return
    try:
        await asyncio.to_thread(lambda: cache.store(prompt=query, response=json.dumps(payload)))
    except Exception as exc:
        logger.debug("semantic cache store failed (%s)", exc)
