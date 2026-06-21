"""Semantic free-resource retrieval via RedisVL vector search + fastembed.

This is HirED's "Redis beyond caching" feature: it embeds the curated free-resource
corpus, stores the vectors in Redis (the Redis Cloud DB), and KNN-searches the most
relevant resources for a user's gap — by *meaning*, not keywords.

Design choices (verified against redisvl 0.20.1 / fastembed 0.8.0):
- Embeddings are FREE + LOCAL: fastembed ONNX `BAAI/bge-small-en-v1.5` (384-dim), no
  PyTorch, no API key, no Anthropic budget.
- RedisVL opens its OWN client from REDIS_URL (not the app's decode_responses client,
  which would corrupt packed vector bytes).
- The index is built once in the BACKGROUND at startup, so it never blocks the app.
- Everything degrades gracefully: if redisvl/fastembed/Redis/the search engine are
  unavailable, `search()` returns None and callers fall back to the static list.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import get_settings
from app.data.resources import RESOURCE_CORPUS

logger = logging.getLogger("hired.resources.vector")

_DIMS = 384  # BAAI/bge-small-en-v1.5
_SCHEMA = {
    "index": {"name": "resources", "prefix": "resource", "storage_type": "hash"},
    "fields": [
        {"name": "name", "type": "text"},
        {"name": "url", "type": "text"},
        {"name": "description", "type": "text"},
        {"name": "gap_category", "type": "tag"},
        {
            "name": "embedding",
            "type": "vector",
            "attrs": {
                "dims": _DIMS,
                "distance_metric": "cosine",
                "algorithm": "flat",
                "datatype": "float32",
            },
        },
    ],
}

_index = None  # AsyncSearchIndex when ready
_embed = None  # callable: str -> list[float]
_status = "not_built"  # not_built | building | ready | failed


def status() -> str:
    return _status


def _build_embedder():
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")  # downloads ~67MB once

    def embed(text: str) -> list[float]:
        return next(iter(model.embed([text]))).tolist()

    return embed


async def build_index() -> None:
    """Create the index + load embedded resources. Idempotent; never raises."""
    global _index, _embed, _status
    if _status in ("building", "ready"):
        return
    _status = "building"
    try:
        from redisvl.index import AsyncSearchIndex

        embed = await asyncio.to_thread(_build_embedder)  # model load is blocking
        index = AsyncSearchIndex.from_dict(_SCHEMA, redis_url=get_settings().redis_url)
        await index.create(overwrite=True, drop=False)
        records = [
            {
                "name": r["name"],
                "url": r["url"],
                "description": r["description"],
                "gap_category": r["gap_category"],
                "embedding": await asyncio.to_thread(embed, f"{r['name']}. {r['description']}"),
            }
            for r in RESOURCE_CORPUS
        ]
        await index.load(records)
        _index, _embed, _status = index, embed, "ready"
        logger.info("semantic resources: index ready (%d resources, %d-dim)", len(records), _DIMS)
    except Exception as exc:  # missing dep, no Redis, no search engine, download fail…
        _index, _embed, _status = None, None, "failed"
        logger.info("semantic resources unavailable (%s) — callers fall back to static list", exc)


def start_build_in_background() -> None:
    """Kick off build_index() without blocking startup (no-op if no event loop)."""
    try:
        asyncio.get_running_loop().create_task(build_index())
    except RuntimeError:
        pass  # no running loop (e.g. import-time / tests)


async def search(query: str, *, k: int = 4) -> Optional[list[dict]]:
    """KNN-search the corpus by meaning. Returns None if unavailable (caller falls back)."""
    if _status != "ready" or _index is None or _embed is None:
        return None
    try:
        from redisvl.query import VectorQuery

        vq = VectorQuery(
            vector=_embed(query),
            vector_field_name="embedding",
            return_fields=["name", "url", "description"],
            num_results=k,
        )
        rows = await _index.query(vq)
        return [
            {"name": r["name"], "url": r["url"], "description": r["description"]}
            for r in rows
            if r.get("name")
        ]
    except Exception as exc:
        logger.warning("semantic resource query failed (%s); falling back", exc)
        return None
