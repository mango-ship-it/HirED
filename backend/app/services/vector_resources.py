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
        import numpy as np
        from redisvl.index import AsyncSearchIndex

        embed = await asyncio.to_thread(_build_embedder)  # model load is blocking
        index = AsyncSearchIndex.from_dict(_SCHEMA, redis_url=get_settings().redis_url)
        # drop=True: clear old docs so a restart rebuilds clean (no duplicate corpus).
        await index.create(overwrite=True, drop=True)
        records = [
            {
                "name": r["name"],
                "url": r["url"],
                "description": r["description"],
                "gap_category": r["gap_category"],
                # HASH vector fields must be packed float32 BYTES, not a Python list.
                "embedding": np.asarray(
                    await asyncio.to_thread(embed, f"{r['name']}. {r['description']}"),
                    dtype=np.float32,
                ).tobytes(),
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


async def search(query: str, *, k: int = 4, max_distance: float | None = None) -> Optional[list[dict]]:
    """KNN-search the index by meaning. `max_distance` drops weak matches (cosine distance,
    0=identical) so a golf query never returns an unrelated generic resource. None if down."""
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
        out: list[dict] = []
        for r in rows:
            if not r.get("name"):
                continue
            if max_distance is not None and float(r.get("vector_distance", 1.0)) > max_distance:
                continue
            out.append({"name": r["name"], "url": r["url"], "description": r["description"]})
        return out
    except Exception as exc:
        logger.warning("semantic resource query failed (%s); falling back", exc)
        return None


async def add_resources(resources: list[dict], *, gap_category: str = "", role: str = "") -> int:
    """Embed + add REAL resources (from Exa) into the live index so it GROWS per role.

    Embeds the title + a real content SNIPPET anchored to the ROLE — NOT the generic
    "free help with {gap}" boilerplate, which would dilute role focus and cause cross-role
    matches. Stores the snippet as the description (richer cards too). Keyed by URL so
    re-adding de-duplicates. Best-effort: a no-op when the index isn't ready.
    """
    if _status != "ready" or _index is None or _embed is None or not resources:
        return 0
    try:
        import hashlib

        import numpy as np

        records, keys = [], []
        for r in resources:
            url = (r.get("url") or "").strip()
            name = (r.get("title") or r.get("name") or "").strip()
            if not url or not name:
                continue
            snippet = (r.get("snippet") or "").strip()
            description = snippet or r.get("description") or r.get("why") or ""
            embed_text = f"{name}. {snippet}".strip(". ").strip()
            if role:
                embed_text = f"{embed_text}. For a {role}."  # anchor the role, drop boilerplate
            records.append({
                "name": name,
                "url": url,
                "description": description,
                "gap_category": gap_category or r.get("type", ""),
                "embedding": np.asarray(_embed(embed_text), dtype=np.float32).tobytes(),
            })
            keys.append("resource:" + hashlib.sha1(url.encode()).hexdigest()[:16])
        if records:
            await _index.load(records, keys=keys)  # URL-based keys -> dedup on re-add
        return len(records)
    except Exception as exc:
        logger.info("add_resources failed (%s)", exc)
        return 0
