"""'People like you' — RedisVL vector similarity over user profiles.

Each scored user's profile (target + the gaps they're working on) is embedded into a
RedisVL index. A new user KNN-searches for past learners with a similar background ->
"people who started where you are also aimed for X; their most common gap was Y." This
index IS the app's growing memory of everyone it has helped (vector search + agent
memory). Seeded with a small, diverse cohort so it works from a cold start, then grows
with real usage. Shared fastembed model (no PyTorch); degrades to None if Redis is down.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Optional

from app.config import get_settings
from app.services.embeddings import DIMS, embed_one, get_model

logger = logging.getLogger("hired.profile_vectors")

_SCHEMA = {
    "index": {"name": "hired_profiles", "prefix": "uprofile", "storage_type": "hash"},
    "fields": [
        {"name": "user_id", "type": "tag"},
        {"name": "target", "type": "text"},
        {"name": "score", "type": "numeric"},
        {"name": "gaps", "type": "text"},
        {
            "name": "embedding",
            "type": "vector",
            "attrs": {"dims": DIMS, "distance_metric": "cosine", "algorithm": "flat", "datatype": "float32"},
        },
    ],
}

# Diverse seed cohort (representative past learners) so "people like you" returns something
# from a cold start. Real users are added on every /score and rank alongside these.
_SEED = [
    {"user_id": "seed-cna-rn", "target": "Registered Nurse", "score": 54, "gaps": "RN license, IV certification, BSN degree"},
    {"user_id": "seed-retail-da", "target": "Data Analyst", "score": 61, "gaps": "SQL, Tableau, statistics, dashboards"},
    {"user_id": "seed-warehouse-cdl", "target": "Truck Driver", "score": 58, "gaps": "CDL Class A, clean driving record, endorsements"},
    {"user_id": "seed-cashier-bookkeeper", "target": "Bookkeeper", "score": 63, "gaps": "QuickBooks, accounting basics, Excel"},
    {"user_id": "seed-server-socialwork", "target": "Social Worker", "score": 49, "gaps": "BSW degree, case management, state licensure"},
    {"user_id": "seed-security-electrician", "target": "Electrician", "score": 52, "gaps": "apprenticeship, NEC code, wiring certification"},
    {"user_id": "seed-callcenter-dev", "target": "Software Developer", "score": 57, "gaps": "Python, data structures, a portfolio project"},
    {"user_id": "seed-hha-ma", "target": "Medical Assistant", "score": 66, "gaps": "CMA certification, phlebotomy, EHR systems"},
]

_index = None  # AsyncSearchIndex when ready
_model = None  # shared fastembed model
_status = "not_built"  # not_built | building | ready | failed


def status() -> str:
    return _status


def _summary(target: str, gaps: str) -> str:
    """The text we embed — a learner's background as 'where they are + where they're going'."""
    return f"Aspiring {target or 'a new career'}. Working to build: {gaps or 'core skills'}."


async def _record(model, p: dict) -> dict:
    import numpy as np

    vec = await asyncio.to_thread(embed_one, model, _summary(p.get("target", ""), p.get("gaps", "")))
    return {
        "user_id": p["user_id"],
        "target": p.get("target", ""),
        "score": int(p.get("score", 0)),
        "gaps": p.get("gaps", ""),
        "embedding": np.asarray(vec, dtype=np.float32).tobytes(),
    }


async def build_index() -> None:
    """Create the profiles index + load the seed cohort. Idempotent; never raises."""
    global _index, _model, _status
    if _status in ("building", "ready"):
        return
    _status = "building"
    try:
        from redisvl.index import AsyncSearchIndex

        model = await get_model()
        if model is None:
            raise RuntimeError("embedder unavailable")
        index = AsyncSearchIndex.from_dict(_SCHEMA, redis_url=get_settings().redis_url)
        await index.create(overwrite=True, drop=True)
        records = [await _record(model, p) for p in _SEED]
        await index.load(records, id_field="user_id")
        _index, _model, _status = index, model, "ready"
        logger.info("profile index ready (%d seed profiles)", len(records))
    except Exception as exc:
        _index, _model, _status = None, None, "failed"
        logger.info("profile index unavailable (%s) — 'people like you' will be empty", exc)


def start_build_in_background() -> None:
    try:
        asyncio.get_running_loop().create_task(build_index())
    except RuntimeError:
        pass


async def add_profile(user_id: str, target: str, score: int, gaps: str) -> None:
    """Upsert this learner into the index (keyed by user_id). Best-effort; never raises."""
    if _status != "ready" or _index is None or _model is None or not user_id:
        return
    try:
        rec = await _record(_model, {"user_id": user_id, "target": target, "score": score, "gaps": gaps})
        await _index.load([rec], id_field="user_id")
    except Exception as exc:
        logger.debug("add_profile failed (%s)", exc)


def _insight(peers: list[dict], gaps: str) -> str:
    """Deterministic cohort insight — most common target + a widely-shared gap."""
    if not peers:
        return ""
    target = Counter(p["target"] for p in peers if p.get("target")).most_common(1)
    gap_words = Counter()
    for p in peers:
        for g in (p.get("gaps") or "").split(","):
            g = g.strip()
            if g:
                gap_words[g.lower()] += 1
    common_gap = gap_words.most_common(1)
    parts = [f"{len(peers)} learner(s) with a background like yours"]
    if target:
        parts.append(f"also worked toward {target[0][0]}")
    line = " ".join(parts) + "."
    if common_gap and common_gap[0][1] > 1:
        line += f" A gap many of them shared: {common_gap[0][0]} — you're not alone in closing it."
    return line


async def people_like_you(
    target: str, gaps: str, *, exclude_user_id: str = "", k: int = 3
) -> Optional[dict]:
    """KNN past learners with a similar background. None if the index is down."""
    if _status != "ready" or _index is None or _model is None:
        return None
    try:
        from redisvl.query import VectorQuery
        from redisvl.query.filter import Tag

        vec = await asyncio.to_thread(embed_one, _model, _summary(target, gaps))
        vq = VectorQuery(
            vector=vec,
            vector_field_name="embedding",
            return_fields=["user_id", "target", "score", "gaps"],
            num_results=k + 1,  # +1 in case we filter out self
        )
        if exclude_user_id:
            vq.set_filter(Tag("user_id") != exclude_user_id)
        results = await _index.query(vq)
        peers = [
            {
                "target": r.get("target", ""),
                "score": int(float(r.get("score", 0))),
                "shared_gaps": [g.strip() for g in (r.get("gaps") or "").split(",") if g.strip()][:3],
                "similarity": round(1 - float(r.get("vector_distance", 1)), 2),
            }
            for r in results
            if r.get("user_id") != exclude_user_id
        ][:k]
        return {"count": len(peers), "peers": peers, "insight": _insight(peers, gaps)}
    except Exception as exc:
        logger.debug("people_like_you failed (%s)", exc)
        return None
