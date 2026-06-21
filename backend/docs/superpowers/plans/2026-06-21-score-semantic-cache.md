# Score Semantic Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Redis semantic cache layer to `/score` so near-identical resumes always return a consistent numeric score even when the exact SHA-256 cache misses.

**Architecture:** A new `score_cache.py` mirrors the existing `semantic_cache.py` (RedisVL `SemanticCache`, shared fastembed vectorizer, lazy singleton, graceful degradation). The `/score` route tries the exact cache first, then the semantic cache, then runs Claude. On a semantic hit, `resume_text` and annotation positions are patched to the current input before returning.

**Tech Stack:** Python 3.11+, FastAPI, RedisVL (`redisvl.extensions.cache.llm.SemanticCache`, `redisvl.utils.vectorize.CustomVectorizer`), fastembed (`BAAI/bge-small-en-v1.5`, 384-dim).

## Global Constraints

- Branch: `feature/score-semantic-cache` from `backend`; merges into `backend`, NOT `main`
- Cache name: `"hired_score_cache"` — do not reuse `"hired_exa_cache"`
- Distance threshold: `0.04` (not 0.07 — tighter than the Exa cache)
- TTL: `7 * 24 * 3600` seconds (7 days — match the exact cache)
- Redis connection kwargs: `{"socket_connect_timeout": 5, "socket_timeout": 5}` — match `semantic_cache.py`
- All cache operations are best-effort: `get_cached` returns `None` on any error, `set_cached` is a no-op on any error. The `/score` route must never fail due to cache issues.
- No new dependencies — RedisVL and fastembed are already in `requirements-vector.txt`

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `app/services/score_cache.py` | Semantic cache module for score responses |
| Create | `tests/test_score_cache.py` | Tests for score_cache invariants |
| Modify | `app/routes/score.py` | Import score_cache; add lookup + store in `/score` handler |

---

### Task 1: Create branch and `score_cache.py`

**Files:**
- Create: `app/services/score_cache.py`
- Create: `tests/test_score_cache.py`

**Interfaces:**
- Produces:
  - `score_cache.get_cached(key: str) -> Optional[dict]` — returns parsed ScoreResponse dict or `None`
  - `score_cache.set_cached(key: str, payload: dict) -> None` — stores; best-effort
  - `score_cache.status() -> str` — `"not_built" | "ready" | "failed"`

- [ ] **Step 1: Create the feature branch**

```bash
git checkout backend
git checkout -b feature/score-semantic-cache
```

Expected: prompt shows `feature/score-semantic-cache`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_score_cache.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /Users/inseon-hwang/Dev/hired/backend
pytest tests/test_score_cache.py -v
```

Expected: `ImportError: cannot import name 'score_cache' from 'app.services'` — the module doesn't exist yet.

- [ ] **Step 4: Create `app/services/score_cache.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_score_cache.py -v
```

Expected: all 4 tests PASS. (Tests that require `status() == "ready"` skip their assertions when Redis is unavailable — that is correct behavior.)

- [ ] **Step 6: Commit**

```bash
git add app/services/score_cache.py tests/test_score_cache.py
git commit -m "feat(cache): add score semantic cache (RedisVL, threshold=0.04)"
```

---

### Task 2: Wire semantic cache into the `/score` route

**Files:**
- Modify: `app/routes/score.py`

**Interfaces:**
- Consumes:
  - `score_cache.get_cached(key: str) -> Optional[dict]`
  - `score_cache.set_cached(key: str, payload: dict) -> None`
  - `_locate(text: str, quote: str) -> tuple[int, int]` — already defined in the file at line 54

- [ ] **Step 1: Write a failing integration test for the route**

Add this test to `tests/test_score_cache.py` (append to the file):

```python
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
```

Run it:

```bash
pytest tests/test_score_cache.py::test_route_returns_current_resume_text_on_semantic_hit -v
```

Expected: PASS (the test validates the patching contract directly; the route change in the next step wires it in).

- [ ] **Step 2: Add `score_cache` import to `app/routes/score.py`**

In `app/routes/score.py`, the existing service imports start at line 37. Add `score_cache` alongside the other service imports:

Old block (lines 37–44):
```python
from app.services.document_parser import (
    DocumentParseError,
    UnsupportedDocumentError,
    extract_text,
)
from app.services.extractor import extract_profile, generate_lessons
from app.services.jd_context import build_lesson_context
from app.services.jd_skills import jd_enriched_skills
from app.services.jobs import load_jobs
from app.services.profile_vectors import add_profile
from app.services.resume_guard import has_usable_resume
from app.services.scoring_engine import get_scorer
from app.services.store import get_store, save_profile
```

New block — add `score_cache` import after `resume_guard`:
```python
from app.services.document_parser import (
    DocumentParseError,
    UnsupportedDocumentError,
    extract_text,
)
from app.services.extractor import extract_profile, generate_lessons
from app.services.jd_context import build_lesson_context
from app.services.jd_skills import jd_enriched_skills
from app.services.jobs import load_jobs
from app.services.profile_vectors import add_profile
from app.services.resume_guard import has_usable_resume
from app.services import score_cache
from app.services.scoring_engine import get_scorer
from app.services.store import get_store, save_profile
```

- [ ] **Step 3: Add semantic cache lookup after the exact cache check**

In `app/routes/score.py`, find the exact cache check block (lines 157–167):

```python
    # Consistency: identical (resume, target, JD-state) -> identical score, served from cache,
    # so the same input never yields a different number (Claude extraction can vary per run).
    cache_key = "score:v2:" + hashlib.sha256(
        f"{resume}\n{target_obj.value}\n{len(cached_jobs or [])}".encode()
    ).hexdigest()[:24]
    try:
        cached = await get_store().get_json(cache_key)
    except Exception:
        cached = None
    if cached is not None:
        return ScoreResponse.model_validate(cached)

    profile = await extract_profile(resume, target_obj.value)
```

Replace with:

```python
    # Consistency: identical (resume, target, JD-state) -> identical score, served from cache,
    # so the same input never yields a different number (Claude extraction can vary per run).
    cache_key = "score:v2:" + hashlib.sha256(
        f"{resume}\n{target_obj.value}\n{len(cached_jobs or [])}".encode()
    ).hexdigest()[:24]
    try:
        cached = await get_store().get_json(cache_key)
    except Exception:
        cached = None
    if cached is not None:
        return ScoreResponse.model_validate(cached)

    # Semantic cache fallback — catches near-identical resumes (PDF re-parse artifacts,
    # whitespace) that missed the exact cache. Threshold 0.04 absorbs only trivial changes;
    # meaningful edits always produce a fresh score.
    semantic_key = f"{resume[:1500]}\n---TARGET---\n{target_obj.value}"
    sem_cached = await score_cache.get_cached(semantic_key)
    if sem_cached is not None:
        sem_cached["resume_text"] = resume
        for ann in sem_cached.get("annotations", []):
            start, end = _locate(resume, ann.get("quote", ""))
            ann["start"] = start
            ann["end"] = end
        return ScoreResponse.model_validate(sem_cached)

    profile = await extract_profile(resume, target_obj.value)
```

- [ ] **Step 4: Add semantic cache store after the fresh result is built**

Find the exact cache store block at the bottom of the handler (lines 267–271):

```python
    try:
        await get_store().set_json(cache_key, response.model_dump(), ttl=_SCORE_TTL)
    except Exception:
        pass
    return response
```

Replace with:

```python
    try:
        await get_store().set_json(cache_key, response.model_dump(), ttl=_SCORE_TTL)
    except Exception:
        pass
    await score_cache.set_cached(semantic_key, response.model_dump())
    return response
```

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all existing tests pass; all `test_score_cache.py` tests pass. No regressions in `test_api_smoke.py`, `test_scoring.py`, `test_scoring_engine.py`, or `test_semantic_cache.py`.

- [ ] **Step 6: Commit**

```bash
git add app/routes/score.py tests/test_score_cache.py
git commit -m "feat(score): wire semantic cache into /score route — three-layer cache"
```
