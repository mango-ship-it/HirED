"""Semantic cache (RedisVL SemanticCache) — the cross-role safety invariant.

The critical guarantee: a cached result for one role must NEVER be returned for a
different role (the templated queries embed close, so the 0.07 threshold is what
keeps them apart). This holds whether the cache is live (tight threshold) or
degraded without Redis (returns None). The hit is checked only when the cache is up.
"""

from __future__ import annotations

import asyncio
import uuid

from app.services import semantic_cache

_NURSE = "people|candidate|LinkedIn profiles of Registered Nurse professionals at a range of career levels:"
_SWDEV = "people|candidate|LinkedIn profiles of Software Developer professionals at a range of career levels:"


def test_cross_role_never_bleeds_and_same_role_hits():
    marker = "RNCARD-" + uuid.uuid4().hex[:6]

    async def main():
        await semantic_cache.set_cached(_NURSE, [{"title": marker}])

        # A DIFFERENT role (same boilerplate template) must NEVER surface the nurse card.
        cross = await semantic_cache.get_cached(_SWDEV)
        assert cross is None or all(c.get("title") != marker for c in cross)

        # The SAME query must hit when the cache is live; None is acceptable when degraded.
        same = await semantic_cache.get_cached(_NURSE)
        if semantic_cache.status() == "ready":
            assert same and any(c.get("title") == marker for c in same)

    asyncio.run(main())
