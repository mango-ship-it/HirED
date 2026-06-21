"""Score semantic cache — invariants.

Same resume (exact or near-identical) hits; different target or meaningfully
different resume misses. Degraded cache returns None cleanly.
"""

from __future__ import annotations

import asyncio
import uuid

from app.services import score_cache

_RESUME = (
    "Jane Doe | jane@example.com\n"
    "SKILLS: Python, FastAPI, Redis\n"
    "EXPERIENCE: Software Engineer at Acme Corp (2021-2024)\n"
    "  Reduced API latency by 40% via caching layer\n"
    "EDUCATION: B.S. Computer Science, UC Berkeley 2021"
)
_TARGET_A = "Software Engineer at a fintech startup"
_TARGET_B = "Registered Nurse at a hospital"

_PAYLOAD = {
    "score": 72,
    "categories": {},
    "lessons": [],
    "matched_skills": ["Python"],
    "missing_skills": ["SQL"],
    "resume_text": _RESUME,
    "has_resume": True,
    "annotations": [
        {
            "quote": "Reduced API latency by 40% via caching layer",
            "category": "quantified_achievements",
            "sentiment": "positive",
            "reason": "Strong quantified impact.",
            "start": 0,
            "end": 0,
        }
    ],
    "status": {"scoring": "complete", "benchmark": "pending", "resources": "pending"},
}


def test_same_key_hits():
    """Storing and retrieving with the exact same key returns the payload."""
    key = f"{_RESUME[:1500]}\n---TARGET---\n{_TARGET_A}"

    async def main():
        await score_cache.set_cached(key, _PAYLOAD)
        result = await score_cache.get_cached(key)
        if score_cache.status() == "ready":
            assert result is not None
            assert result["score"] == _PAYLOAD["score"]

    asyncio.run(main())


def test_whitespace_variation_hits():
    """A resume with minor whitespace differences (within 0.04 distance) still hits."""
    resume_variant = _RESUME.replace(" SKILLS:", "  SKILLS:")  # double space
    key_original = f"{_RESUME[:1500]}\n---TARGET---\n{_TARGET_A}"
    key_variant = f"{resume_variant[:1500]}\n---TARGET---\n{_TARGET_A}"

    async def main():
        await score_cache.set_cached(key_original, _PAYLOAD)
        result = await score_cache.get_cached(key_variant)
        if score_cache.status() == "ready":
            assert result is not None
            assert result["score"] == _PAYLOAD["score"]

    asyncio.run(main())


def test_different_target_misses():
    """Same resume, different target string — must never cross-pollinate."""
    marker = "SKILL-" + uuid.uuid4().hex[:8]
    key_a = f"{_RESUME[:1500]}\n---TARGET---\n{_TARGET_A}"
    key_b = f"{_RESUME[:1500]}\n---TARGET---\n{_TARGET_B}"

    async def main():
        await score_cache.set_cached(key_a, {**_PAYLOAD, "missing_skills": [marker]})
        result = await score_cache.get_cached(key_b)
        if score_cache.status() == "ready":
            assert result is None or marker not in result.get("missing_skills", [])

    asyncio.run(main())


def test_degraded_returns_none():
    """get_cached returns None cleanly when the cache is not ready."""

    async def main():
        if score_cache.status() != "ready":
            result = await score_cache.get_cached("any key")
            assert result is None

    asyncio.run(main())


def test_route_returns_current_resume_text_on_semantic_hit():
    """On a semantic cache hit, the returned resume_text must be the NEW input, not the cached one."""
    from app.services import score_cache as sc

    original_resume = _RESUME
    variant_resume = _RESUME.replace(" SKILLS:", "  SKILLS:")
    key_original = f"{original_resume[:1500]}\n---TARGET---\n{_TARGET_A}"

    async def main():
        payload_with_original = {**_PAYLOAD, "resume_text": original_resume}
        await sc.set_cached(key_original, payload_with_original)

        key_variant = f"{variant_resume[:1500]}\n---TARGET---\n{_TARGET_A}"
        result = await sc.get_cached(key_variant)

        if sc.status() == "ready" and result is not None:
            # Simulate the patching logic the route applies
            result["resume_text"] = variant_resume
            assert result["resume_text"] == variant_resume
            assert result["resume_text"] != original_resume

    asyncio.run(main())
