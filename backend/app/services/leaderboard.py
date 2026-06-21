"""Live readiness percentile via Redis Sorted Sets — a classic 'leaderboard', beyond caching.

Every scored user's readiness goes into `readiness:{role}` (ZADD, member = user_id). "How you
compare" then reads a REAL population rank with ZCOUNT/ZCARD — O(log n), growing with every user.
Seeded lazily with a synthetic cohort per role so the percentile is meaningful from day one.
Sorted sets have no in-memory fallback here — if Redis is down we return None and the caller
falls back to its derived percentile.
"""

from __future__ import annotations

import hashlib
import logging
import random
import re
from typing import Optional

from app.services.store import get_store

logger = logging.getLogger("hired.leaderboard")

_MIN_COHORT = 8     # need at least this many scores for a meaningful percentile
_SEED_COUNT = 40    # synthetic users seeded per role (bootstrap, then real users accrue)
_seeded: set = set()  # roles seeded this process (in-process guard; Redis-side is idempotent)


def _key(role: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (role or "").lower()).strip("-") or "general"
    return f"readiness:{slug}"


def _seed_for(key: str) -> dict[str, float]:
    """A reproducible, realistic synthetic readiness distribution for a role (N(55, 17))."""
    seed = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    return {f"synthetic:{i}": float(max(10, min(95, round(rng.gauss(55, 17))))) for i in range(_SEED_COUNT)}


async def _ensure_seeded(redis, key: str) -> None:
    """Seed a role's leaderboard with a synthetic cohort once (idempotent — skips if already filled)."""
    if key in _seeded:
        return
    _seeded.add(key)
    try:
        if await redis.zcard(key) < _SEED_COUNT:
            await redis.zadd(key, _seed_for(key))
    except Exception as exc:
        logger.debug("leaderboard seed failed (%s)", exc)


async def add_score(role: str, user_id: str, score: int) -> None:
    """Record/refresh a user's readiness in the role leaderboard (ZADD upsert by user_id)."""
    redis = get_store().raw()
    if redis is None or not role or not user_id:
        return
    try:
        key = _key(role)
        await _ensure_seeded(redis, key)
        await redis.zadd(key, {user_id: float(score)})
    except Exception as exc:
        logger.debug("leaderboard add failed (%s)", exc)


async def percentile(role: str, score: int) -> Optional[int]:
    """Percentile of `score` among everyone targeting `role` — the 'ahead of X%' figure.
    None when Redis is down or the cohort is too small to be meaningful."""
    redis = get_store().raw()
    if redis is None or not role:
        return None
    try:
        key = _key(role)
        await _ensure_seeded(redis, key)
        total = int(await redis.zcard(key))
        if total < _MIN_COHORT:
            return None
        below = int(await redis.zcount(key, "-inf", f"({float(score)}"))  # strictly below this score
        return max(1, min(99, round(100 * below / total)))
    except Exception as exc:
        logger.debug("leaderboard percentile failed (%s)", exc)
        return None


async def cohort_size(role: str) -> int:
    """How many scores are in this role's leaderboard (synthetic + real). 0 if Redis is down."""
    redis = get_store().raw()
    if redis is None or not role:
        return 0
    try:
        return int(await redis.zcard(_key(role)))
    except Exception:
        return 0
