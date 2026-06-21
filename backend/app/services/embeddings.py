"""Shared fastembed embedder — BAAI/bge-small-en-v1.5 (384-dim, ONNX, no PyTorch).

ONE model instance reused across the RedisVL features that need embeddings — the
SemanticCache over Exa lookups and the "people like you" profile index — so we
load the ~67MB model once. Loaded lazily off the event loop; every accessor
degrades to None if fastembed / the model download is unavailable, so callers
fall back gracefully.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("hired.embeddings")

DIMS = 384
_MODEL_NAME = "BAAI/bge-small-en-v1.5"

_model = None
_failed = False
_lock = asyncio.Lock()


def _load_model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=_MODEL_NAME)


async def get_model():
    """Lazily load the shared fastembed model (blocking load off-loop). None if unavailable."""
    global _model, _failed
    if _model is not None:
        return _model
    if _failed:
        return None
    async with _lock:
        if _model is None and not _failed:
            try:
                _model = await asyncio.to_thread(_load_model)
                logger.info("shared embedder ready (%s, %d-dim)", _MODEL_NAME, DIMS)
            except Exception as exc:  # missing dep / download failure / offline
                _failed = True
                logger.info("shared embedder unavailable (%s)", exc)
    return _model


def embed_one(model, text: str) -> list[float]:
    """Embed a single string with an already-loaded model (sync)."""
    return next(iter(model.embed([text]))).tolist()


async def embed(text: str):
    """Embed text with the shared model. None if embeddings are unavailable."""
    model = await get_model()
    if model is None:
        return None
    return await asyncio.to_thread(embed_one, model, text)
