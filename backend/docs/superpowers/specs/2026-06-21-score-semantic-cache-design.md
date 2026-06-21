# Score Semantic Cache Design

**Date:** 2026-06-21  
**Branch:** `feature/score-semantic-cache` (from `backend`)  
**Merges into:** `backend`

## Problem

The `/score` route has an exact SHA-256 cache keyed on `(resume text, target, JD count)`. When that cache misses — due to JD count changes, Redis unavailability, or subtle PDF re-parse byte differences — Claude re-extracts the profile and the deterministic scorer can produce a different numeric score for what is semantically the same resume. Users experience their score fluctuating across submissions even when they have not meaningfully changed their resume.

## Solution

Add a **semantic cache layer** between the existing exact cache and the live Claude call. Two near-identical resumes (cosine distance ≤ 0.04) targeting the same role return the same cached score. The exact cache remains the primary (fast, precise) layer; the semantic cache is a fallback safety net.

## Architecture

Three-layer cache in `/score`, tried in order:

```
POST /score
  │
  ├─ 1. Exact cache (SHA-256 of resume + target + JD count)
  │       Redis key: "score:v2:<hash>"   TTL: 7 days
  │       Hit → return immediately
  │
  ├─ 2. Semantic cache (new)
  │       RedisVL SemanticCache  name: "hired_score_cache"
  │       Threshold: 0.04   TTL: 7 days
  │       Hit → patch resume_text + recompute annotation positions → return
  │
  └─ 3. Fresh Claude call + deterministic scorer
          → write result to semantic cache AND exact cache
```

### New file: `app/services/score_cache.py`

Mirrors `app/services/semantic_cache.py` exactly:
- Lazy singleton init behind `asyncio.Lock`
- `CustomVectorizer` wrapping the shared fastembed model (via `embed_one` / `get_model`)
- `RedisVL SemanticCache` with `name="hired_score_cache"`, `distance_threshold=0.04`, `ttl=7*24*3600`
- Same Redis connection kwargs (`socket_connect_timeout=5`, `socket_timeout=5`)
- `get_cached(key) -> Optional[dict]` — returns parsed JSON or `None`
- `set_cached(key, payload: dict) -> None` — stores JSON; best-effort, never raises
- `status() -> str` — `"not_built" | "ready" | "failed"`

## Embedding Key

```python
semantic_key = f"{resume[:1500]}\n---TARGET---\n{target}"
```

- First 1500 chars of the resume cover the header, skills block, and first job — where the majority of scoring signal lives — while staying within the fastembed model's token window.
- `---TARGET---` separator prevents the target string from blending into the resume embedding and ensures cross-target isolation (different target → different vector region → no cross-role hit).

## Semantic Cache Hit Patching

A cached `ScoreResponse` contains `resume_text` and annotation `(start, end)` character offsets computed against the original resume. On a semantic hit, the current resume may differ by whitespace or minor formatting. Before returning:

1. Replace `cached["resume_text"]` with the current `resume` string.
2. For each annotation in `cached["annotations"]`, re-run `_locate(resume, annotation["quote"])` to recompute `(start, end)` against the new text.
3. Return the patched dict as `ScoreResponse.model_validate(patched)`.

`_locate()` already has a whitespace-tolerant regex fallback. At ≤0.04 distance, quotes from the cached extraction will be present in the new text in all realistic cases. If a quote is not found, `_locate` returns `(-1, -1)` — the frontend already handles this gracefully.

The score, categories, lessons, matched_skills, and missing_skills are returned unchanged from the cache.

## Threshold Rationale

| Distance | Meaning |
|----------|---------|
| 0.00 | Byte-identical |
| ~0.02–0.03 | PDF re-parse whitespace/encoding artifacts |
| ~0.04 | Minor formatting differences (line breaks, punctuation) |
| ~0.07 | Exa query paraphrase (current Exa threshold) |
| ~0.10+ | Meaningful content change (added skill, new bullet) |

0.04 absorbs only trivial variations. A user adding a skill, rewriting a bullet, or fixing a substantive typo exceeds 0.04 and gets a fresh score.

## Error Handling & Degradation

The cache is always best-effort. The `/score` route never fails due to cache unavailability:

- Redis unavailable → `get_cached` returns `None`, `set_cached` is a no-op
- RedisVL / RediSearch module not installed → `_status = "failed"`, all calls return `None` / no-op
- Malformed cached JSON → exception caught, returns `None`, falls through to fresh call
- `_locate()` miss on re-patching → returns `(-1, -1)`, frontend handles gracefully

Degradation path is identical to `semantic_cache.py`.

## Changes to `/score` Route

In `app/routes/score.py`, after the existing exact cache check and before `extract_profile`:

```python
# Semantic cache fallback (fires only on exact cache miss)
semantic_key = f"{resume[:1500]}\n---TARGET---\n{target_obj.value}"
sem_cached = await score_cache.get_cached(semantic_key)
if sem_cached is not None:
    # Patch resume_text and recompute annotation positions for the current input
    sem_cached["resume_text"] = resume
    for ann in sem_cached.get("annotations", []):
        start, end = _locate(resume, ann.get("quote", ""))
        ann["start"] = start
        ann["end"] = end
    return ScoreResponse.model_validate(sem_cached)
```

After the fresh result is built (before `return response`), add:

```python
await score_cache.set_cached(semantic_key, response.model_dump())
```

## Testing

New file: `tests/test_score_cache.py`

| Test | Expected |
|------|----------|
| Same resume, whitespace variation (e.g. `" "` → `"  "`) | Semantic hit; returned `resume_text` is the new text; annotation positions recomputed |
| Meaningfully edited resume (added bullet) | Semantic miss → returns `None` |
| Same resume, different target | Semantic miss → no cross-target hit |
| Cache degraded (Redis down) | `get_cached` returns `None` cleanly; no exception |

Follow the pattern in `tests/test_semantic_cache.py`: async `main()` run with `asyncio.run()`, guard hits on `score_cache.status() == "ready"`.

## Branch & Merge Plan

1. Create `feature/score-semantic-cache` from `backend`
2. Implement and test
3. PR into `backend` (not `main`)
