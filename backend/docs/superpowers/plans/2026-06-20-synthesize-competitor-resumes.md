# Synthesize Competitor Resumes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `_SEED_COMPETITORS` in `benchmark_agent.py` with JD-aware competitor resumes synthesized via TokenRouter, wired into a proper ELO-based percentile pipeline.

**Architecture:** A new `app/services/resume_synthesizer.py` generates 8 fictional competitor resumes (2 strong / 4 average / 2 weak) from the real JD text using TokenRouter. `benchmark_agent.py` calls the synthesizer, runs all 8 judgements in parallel via `asyncio.gather`, and converts the ELO results to a percentile using the existing `elo_update` + `rating_to_percentile` functions. Static fallback resumes ensure the demo never hard-fails without a TokenRouter key.

**Tech Stack:** Python 3.12, AsyncOpenAI (OpenAI-compatible, points at TokenRouter), asyncio, existing `app/services/elo.py` + `app/services/twoafc_judge.py`

## Why 8 Competitors (2 strong + 4 average + 2 weak)

With N=8 the user's win count can be 0–8, giving **9 distinct percentile outcomes** (0%, 12%, 25%, 37%, 50%, 62%, 75%, 87%, 100%). The 3-tier distribution ensures a realistic bell-curve cohort so the percentile is never trivially 0% or 100%:
- **Strong (2):** top-tier candidates the user must beat to crack the 75th+ percentile
- **Average (4):** realistic peers — where most users land (37–62%)
- **Weak (2):** floor candidates that only very weak users lose to

Total TokenRouter cost per benchmark run: ~8 synthesis calls + 8 judge calls ≈ **$0.02**.

## Global Constraints

- Do NOT modify `app/models/schemas.py` — the API contract is locked (frontend depends on it)
- Do NOT modify `agents/messages.py` `BenchmarkRequest` fields — changing the wire schema breaks the running agent
- `judge_pair(resume_a, resume_b, jd)` returns `'A'` or `'B'` (user is always `A`)
- `elo_update(rating_a, rating_b, winner)` returns `(new_a, new_b)` — both float
- `rating_to_percentile(user_rating, cohort_ratings)` returns `int` 0–100
- Fallback: when `TOKEN_ROUTER_API_KEY` is absent or synthesis fails, use static per-tier seed resumes — never raise, never crash
- `python3` is the Python binary (not `python`)
- Run tests from `backend/`: `python3 -m pytest tests/test_resume_synthesizer.py -v`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| **Create** | `app/services/resume_synthesizer.py` | Synthesis via TokenRouter + static fallbacks |
| **Create** | `tests/test_resume_synthesizer.py` | Unit tests for synthesis (mocked TokenRouter) |
| **Modify** | `agents/benchmark_agent.py` | Replace `_SEED_COMPETITORS` with synthesized cohort; use `elo_update` + `rating_to_percentile`; parallel judging |

---

### Task 1: `app/services/resume_synthesizer.py`

**Files:**
- Create: `app/services/resume_synthesizer.py`
- Test: `tests/test_resume_synthesizer.py`

**Interfaces:**
- Consumes: `app.config.get_settings()` (for `token_router_api_key`, `token_router_base_url`, `token_router_model`)
- Produces:
  - `Tier = Literal["strong", "average", "weak"]`
  - `async def synthesize_resume(jd: str, tier: Tier, target: str) -> str`
  - `async def synthesize_cohort(jd: str, target: str, *, n_strong: int = 2, n_average: int = 4, n_weak: int = 2) -> list[str]`

- [ ] **Step 1: Write failing tests**

Create `tests/test_resume_synthesizer.py`:

```python
"""Tests for app/services/resume_synthesizer.py."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.resume_synthesizer import (
    Tier,
    _fallback_for_tier,
    synthesize_cohort,
    synthesize_resume,
)


# ── _fallback_for_tier ────────────────────────────────────────────────────────

def test_fallback_strong_returns_nonempty():
    text = _fallback_for_tier("strong")
    assert isinstance(text, str) and len(text) > 50


def test_fallback_average_returns_nonempty():
    text = _fallback_for_tier("average")
    assert isinstance(text, str) and len(text) > 50


def test_fallback_weak_returns_nonempty():
    text = _fallback_for_tier("weak")
    assert isinstance(text, str) and len(text) > 50


# ── synthesize_resume ─────────────────────────────────────────────────────────

_FAKE_JD = "Software Engineer Intern — Python, ML experience preferred."
_FAKE_TARGET = "ML Engineer Intern"


def _make_openai_response(content: str):
    """Build a minimal mock that looks like an AsyncOpenAI chat completion."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_synthesize_resume_uses_tokenrouter_when_key_present():
    fake_resume = "Jane Doe | ML Intern\nEducation: BS CS, MIT GPA 3.9"
    mock_response = _make_openai_response(fake_resume)

    with patch("app.services.resume_synthesizer.get_settings") as mock_cfg, \
         patch("app.services.resume_synthesizer.AsyncOpenAI") as mock_cls:
        settings = MagicMock()
        settings.token_router_api_key = "tr-fake-key"
        settings.token_router_base_url = "https://api.tokenrouter.com/v1"
        settings.token_router_model = "auto"
        mock_cfg.return_value = settings

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        result = await synthesize_resume(_FAKE_JD, "strong", _FAKE_TARGET)

    assert result == fake_resume


@pytest.mark.asyncio
async def test_synthesize_resume_falls_back_when_no_key():
    with patch("app.services.resume_synthesizer.get_settings") as mock_cfg:
        settings = MagicMock()
        settings.token_router_api_key = ""
        mock_cfg.return_value = settings

        result = await synthesize_resume(_FAKE_JD, "average", _FAKE_TARGET)

    assert isinstance(result, str) and len(result) > 50


@pytest.mark.asyncio
async def test_synthesize_resume_falls_back_on_exception():
    with patch("app.services.resume_synthesizer.get_settings") as mock_cfg, \
         patch("app.services.resume_synthesizer.AsyncOpenAI") as mock_cls:
        settings = MagicMock()
        settings.token_router_api_key = "tr-fake-key"
        settings.token_router_base_url = "https://api.tokenrouter.com/v1"
        settings.token_router_model = "auto"
        mock_cfg.return_value = settings

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("network error")
        )
        mock_cls.return_value = mock_client

        result = await synthesize_resume(_FAKE_JD, "weak", _FAKE_TARGET)

    assert isinstance(result, str) and len(result) > 50


@pytest.mark.asyncio
async def test_synthesize_resume_falls_back_on_too_short_response():
    """If the model returns suspiciously short text, fall back to static."""
    mock_response = _make_openai_response("ok")

    with patch("app.services.resume_synthesizer.get_settings") as mock_cfg, \
         patch("app.services.resume_synthesizer.AsyncOpenAI") as mock_cls:
        settings = MagicMock()
        settings.token_router_api_key = "tr-fake-key"
        settings.token_router_base_url = "https://api.tokenrouter.com/v1"
        settings.token_router_model = "auto"
        mock_cfg.return_value = settings

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        result = await synthesize_resume(_FAKE_JD, "strong", _FAKE_TARGET)

    # fallback kicks in because response is < 100 chars
    assert len(result) > 50


# ── synthesize_cohort ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesize_cohort_default_returns_8():
    fake = "Jane Doe | Role\nEducation: BS CS, MIT"

    async def _fake_synthesize(jd, tier, target):
        return fake

    with patch("app.services.resume_synthesizer.synthesize_resume", side_effect=_fake_synthesize):
        result = await synthesize_cohort(_FAKE_JD, _FAKE_TARGET)

    assert len(result) == 8


@pytest.mark.asyncio
async def test_synthesize_cohort_custom_counts():
    fake = "Jane Doe | Role\nEducation: BS CS, MIT"

    async def _fake_synthesize(jd, tier, target):
        return fake

    with patch("app.services.resume_synthesizer.synthesize_resume", side_effect=_fake_synthesize):
        result = await synthesize_cohort(_FAKE_JD, _FAKE_TARGET, n_strong=1, n_average=2, n_weak=1)

    assert len(result) == 4


@pytest.mark.asyncio
async def test_synthesize_cohort_returns_list_of_strings():
    fake = "Jane Doe | Role\nEducation: BS CS, MIT"

    async def _fake_synthesize(jd, tier, target):
        return fake

    with patch("app.services.resume_synthesizer.synthesize_resume", side_effect=_fake_synthesize):
        result = await synthesize_cohort(_FAKE_JD, _FAKE_TARGET)

    assert all(isinstance(r, str) for r in result)
```

- [ ] **Step 2: Run tests — confirm they FAIL**

```bash
cd backend && python3 -m pytest tests/test_resume_synthesizer.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'app.services.resume_synthesizer'`

- [ ] **Step 3: Create `app/services/resume_synthesizer.py`**

```python
"""Synthesize fictional competitor resumes from a JD via TokenRouter.

Used by benchmark_agent.py to replace the hardcoded _SEED_COMPETITORS with
JD-aware, tier-stratified profiles so the percentile reflects real role requirements.

Tier distribution (default): 2 strong + 4 average + 2 weak = 8 competitors.
Falls back to static seeds when TOKEN_ROUTER_API_KEY is absent or a call fails.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Literal

from app.config import get_settings

logger = logging.getLogger("hired.synthesizer")

Tier = Literal["strong", "average", "weak"]

# ── Static fallback cohort — one per tier, diverse roles ─────────────────────

_FALLBACK: dict[str, list[str]] = {
    "strong": [
        (
            "Jordan Park | ML Engineer\n"
            "Education: MS Computer Science, Stanford University, GPA 3.9 (2023)\n"
            "Experience:\n"
            "  - ML Research Intern @ Google DeepMind (Jun–Dec 2022, 6 mo)\n"
            "    * Fine-tuned LLaMA-2 for domain QA; BLEU score +18% vs. baseline\n"
            "    * Reduced inference latency 40% via INT8 quantization; deployed to 2M users\n"
            "  - Research Assistant @ Stanford NLP Group (Jan–May 2022, 5 mo)\n"
            "    * Co-authored paper accepted at ACL 2023; 120 citations in 6 months\n"
            "Skills: PyTorch, TensorFlow, Python, CUDA, MLflow, Docker, Kubernetes\n"
            "Projects: Open-source RAG library (3.4k GitHub stars)"
        ),
        (
            "Riley Okonkwo | Software Engineering Intern\n"
            "Education: BS Computer Science, MIT, GPA 3.95 (2024)\n"
            "Experience:\n"
            "  - SWE Intern @ Stripe (Summer 2023, 3 mo)\n"
            "    * Built real-time fraud detection feature; blocked $2.1M/mo in fraud\n"
            "    * Reduced API p99 latency from 420 ms to 90 ms via query optimization\n"
            "  - SWE Intern @ Jane Street (Summer 2022, 3 mo)\n"
            "    * Implemented trading algo in OCaml; 15% P&L improvement over baseline\n"
            "Skills: Python, Go, Java, PostgreSQL, Redis, Kafka, AWS\n"
            "Projects: Distributed key-value store (capstone, 2k GitHub stars)"
        ),
    ],
    "average": [
        (
            "Sam Torres | Software Developer\n"
            "Education: BS Computer Science, University of Illinois, GPA 3.4 (2023)\n"
            "Experience:\n"
            "  - Software Intern @ Midwest Fintech (Jun–Aug 2022, 3 mo)\n"
            "    * Developed REST APIs for payment processing; handled 500 req/day\n"
            "    * Fixed 12 production bugs, reducing error rate 20%\n"
            "Skills: Python, JavaScript, React, SQL, Git, Linux\n"
            "Projects: Budget tracking app (50 GitHub stars); web scraper"
        ),
        (
            "Casey Liu | CS Graduate\n"
            "Education: BS Computer Science, UC San Diego, GPA 3.2 (2024)\n"
            "Experience:\n"
            "  - IT Intern @ Healthcare Startup (Sep–Dec 2023, 4 mo)\n"
            "    * Automated data pipeline, saving team 3 hrs/week\n"
            "    * Maintained CI/CD for 4 microservices\n"
            "Skills: Python, TypeScript, Node.js, MySQL, Docker\n"
            "Projects: NLP sentiment analyzer; class schedule optimizer (200 users)"
        ),
        (
            "Morgan Hayes | Entry-Level Engineer\n"
            "Education: BS Computer Engineering, Texas A&M, GPA 3.1 (2023)\n"
            "Experience:\n"
            "  - Backend Intern @ E-commerce Startup (Jan–Apr 2023, 4 mo)\n"
            "    * Migrated 5 legacy PHP endpoints to Node.js\n"
            "    * Increased test coverage from 40% to 65%\n"
            "Skills: JavaScript, Python, PHP, MongoDB, Express, Git\n"
            "Projects: Discord bot (1k active users)"
        ),
        (
            "Drew Kim | Junior Developer\n"
            "Education: BS Information Systems, Purdue University, GPA 3.0 (2023)\n"
            "Experience:\n"
            "  - Research Assistant @ Purdue CS Lab (Aug 2022–May 2023, 9 mo)\n"
            "    * Labeled 10k-image dataset for computer vision research\n"
            "    * Automated data cleaning with Python scripts; saved 4 hrs/week\n"
            "Skills: Python, Java, R, SQL, Tableau\n"
            "Projects: Movie recommendation system"
        ),
    ],
    "weak": [
        (
            "Alex Smith | Aspiring Developer\n"
            "Education: Associate's Degree in Information Technology (2023)\n"
            "Experience:\n"
            "  - IT Help Desk @ Local School District (2022–2023, 1 yr)\n"
            "    * Assisted staff with computer issues and software installation\n"
            "  - Self-taught programmer (6 months of online courses)\n"
            "Skills: HTML, CSS, basic Python, Microsoft Office\n"
            "Projects: Personal website; to-do list app (tutorial-based)"
        ),
        (
            "Jamie Wilson | Career Changer\n"
            "Education: BA English Literature, State University (2020)\n"
            "Experience:\n"
            "  - Barista @ Local Coffee Shop (2020–2023, 3 yr)\n"
            "    * Managed daily operations and trained 3 new employees\n"
            "  - 3-month coding bootcamp graduate (2023)\n"
            "Skills: HTML, CSS, JavaScript basics, Python basics\n"
            "Projects: Blog website; weather app (bootcamp project)"
        ),
    ],
}

_TIER_DESCRIPTION: dict[str, str] = {
    "strong": (
        "an excellent fit: 2+ relevant internships with quantified achievements "
        "(%, $, user counts), top-tier education (GPA 3.7+), full skill-set match. "
        "Include at least 3 quantified bullet points with real numbers."
    ),
    "average": (
        "a decent but not outstanding fit: 1-2 partially relevant experiences, "
        "some quantified results but not all, solid education (GPA 3.0-3.5), "
        "most but not all required skills. Include 1-2 quantified bullets."
    ),
    "weak": (
        "a poor fit: minimal relevant experience (self-taught or bootcamp background), "
        "no quantified achievements, only basic skill overlap with the JD requirements."
    ),
}

_SYNTHESIS_SYSTEM = (
    "You generate realistic fictional competitor resumes for a hiring benchmark. "
    "Produce ONLY a plain-text resume — no JSON, no preamble, no explanation. "
    "Use exactly this format:\n"
    "Full Name | Target Role\n"
    "Education: Degree, Institution, GPA (Year)\n"
    "Experience:\n"
    "  - Role @ Company (dates, duration)\n"
    "    * Achievement bullet\n"
    "Skills: comma-separated list\n"
    "Projects: name (brief description)"
)


def _fallback_for_tier(tier: Tier) -> str:
    """Return one static fallback resume for the given tier."""
    return random.choice(_FALLBACK[tier])


async def synthesize_resume(jd: str, tier: Tier, target: str) -> str:
    """Generate one competitor resume via TokenRouter at the given quality tier.

    Falls back to a static seed when TOKEN_ROUTER_API_KEY is absent or the call fails.
    """
    settings = get_settings()
    if not settings.token_router_api_key:
        logger.debug("TOKEN_ROUTER_API_KEY not set; using static fallback for tier=%s", tier)
        return _fallback_for_tier(tier)

    prompt = (
        f"Generate a realistic fictional resume for a candidate who is "
        f"{_TIER_DESCRIPTION[tier]}\n\n"
        f"TARGET ROLE: {target}\n\n"
        f"JOB DESCRIPTION (first 1500 chars):\n{jd[:1500]}\n\n"
        "Produce the resume in the plain-text format specified. Make the candidate "
        "believable and internally consistent. Do NOT use names of real public figures."
    )

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.token_router_api_key,
            base_url=settings.token_router_base_url,
        )
        response = await client.chat.completions.create(
            model=settings.token_router_model,
            messages=[
                {"role": "system", "content": _SYNTHESIS_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.8,
        )
        text = (response.choices[0].message.content or "").strip()
        if len(text) > 100:
            return text
        logger.warning("Synthesizer returned too-short response (tier=%s); using fallback", tier)
        return _fallback_for_tier(tier)
    except Exception as exc:
        logger.warning("Resume synthesis failed (tier=%s): %s; using fallback", tier, exc)
        return _fallback_for_tier(tier)


async def synthesize_cohort(
    jd: str,
    target: str,
    *,
    n_strong: int = 2,
    n_average: int = 4,
    n_weak: int = 2,
) -> list[str]:
    """Synthesize a full competitor cohort in parallel.

    Default: 2 strong + 4 average + 2 weak = 8 resumes.
    Returns a shuffled list so position bias doesn't affect the judge.
    """
    tasks = (
        [synthesize_resume(jd, "strong", target) for _ in range(n_strong)]
        + [synthesize_resume(jd, "average", target) for _ in range(n_average)]
        + [synthesize_resume(jd, "weak", target) for _ in range(n_weak)]
    )
    resumes = list(await asyncio.gather(*tasks))
    random.shuffle(resumes)
    return resumes
```

- [ ] **Step 4: Run tests — confirm they PASS**

```bash
cd backend && python3 -m pytest tests/test_resume_synthesizer.py -v
```

Expected: 9 tests, all PASSED.

- [ ] **Step 5: Run full suite — no regressions**

```bash
cd backend && python3 -m pytest --tb=short -q 2>&1 | tail -5
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/resume_synthesizer.py backend/tests/test_resume_synthesizer.py
git commit -m "feat(benchmark): JD-aware competitor resume synthesizer via TokenRouter"
```

---

### Task 2: Wire synthesized cohort + proper ELO into `benchmark_agent.py`

**Files:**
- Modify: `agents/benchmark_agent.py`

**Interfaces:**
- Consumes (from Task 1):
  - `from app.services.resume_synthesizer import synthesize_cohort`
  - `synthesize_cohort(jd: str, target: str, *, n_strong=2, n_average=4, n_weak=2) -> list[str]`
- Consumes (already imported): `judge_pair(resume_a, resume_b, jd) -> str`
- Consumes (existing, import change needed):
  - `from app.services.elo import elo_update, rating_to_percentile` (replacing current `run_tournament, win_rate_to_percentile`)
  - `elo_update(rating_a: float, rating_b: float, winner: str) -> tuple[float, float]`
  - `rating_to_percentile(user_rating: float, cohort_ratings: list[float]) -> int`

**What changes in `benchmark_agent.py`:**

1. **Import line** — change:
   ```python
   from app.services.elo import run_tournament, win_rate_to_percentile
   ```
   to:
   ```python
   from app.services.elo import elo_update, rating_to_percentile
   ```

2. **Add import** after the elo import:
   ```python
   from app.services.resume_synthesizer import synthesize_cohort
   ```

3. **Replace `_run_2afc_pipeline`** entirely — new version runs synthesis + parallel judging + ELO.

4. **Keep `_SEED_COMPETITORS`** as the fallback (the synthesizer already has its own tier-based fallbacks, but the agent-level fallback guards against synthesizer timeout).

- [ ] **Step 1: Write the failing integration test**

Add `tests/test_benchmark_pipeline.py`:

```python
"""Integration tests for the 2AFC + ELO pipeline in benchmark_agent."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_2afc_pipeline_returns_int_percentile():
    """_run_2afc_pipeline should return (percentile: int, sample_size: int)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from agents.benchmark_agent import _run_2afc_pipeline

    fake_competitors = ["Candidate A resume text"] * 8

    with patch("agents.benchmark_agent.synthesize_cohort", new=AsyncMock(return_value=fake_competitors)), \
         patch("agents.benchmark_agent.judge_pair", new=AsyncMock(return_value="A")), \
         patch("agents.benchmark_agent._load_jd", return_value="Software Engineer JD"):
        percentile, sample_size = await _run_2afc_pipeline("User resume proxy", "SWE Intern")

    assert isinstance(percentile, int)
    assert 0 <= percentile <= 100
    assert sample_size == 8


@pytest.mark.asyncio
async def test_run_2afc_pipeline_user_wins_all_gives_high_percentile():
    """If user beats all 8 competitors, percentile should be 100."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from agents.benchmark_agent import _run_2afc_pipeline

    fake_competitors = ["Competitor resume"] * 8

    with patch("agents.benchmark_agent.synthesize_cohort", new=AsyncMock(return_value=fake_competitors)), \
         patch("agents.benchmark_agent.judge_pair", new=AsyncMock(return_value="A")), \
         patch("agents.benchmark_agent._load_jd", return_value="JD text"):
        percentile, _ = await _run_2afc_pipeline("User proxy", "ML Intern")

    assert percentile == 100


@pytest.mark.asyncio
async def test_run_2afc_pipeline_user_loses_all_gives_low_percentile():
    """If user loses all 8, percentile should be 0."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from agents.benchmark_agent import _run_2afc_pipeline

    fake_competitors = ["Competitor resume"] * 8

    with patch("agents.benchmark_agent.synthesize_cohort", new=AsyncMock(return_value=fake_competitors)), \
         patch("agents.benchmark_agent.judge_pair", new=AsyncMock(return_value="B")), \
         patch("agents.benchmark_agent._load_jd", return_value="JD text"):
        percentile, _ = await _run_2afc_pipeline("User proxy", "ML Intern")

    assert percentile == 0


@pytest.mark.asyncio
async def test_run_2afc_pipeline_falls_back_on_synthesis_timeout():
    """If synthesize_cohort times out, _SEED_COMPETITORS is used as fallback."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from agents.benchmark_agent import _run_2afc_pipeline, _SEED_COMPETITORS

    async def _slow_synthesis(*args, **kwargs):
        await asyncio.sleep(9999)
        return []

    with patch("agents.benchmark_agent.synthesize_cohort", side_effect=_slow_synthesis), \
         patch("agents.benchmark_agent.judge_pair", new=AsyncMock(return_value="A")), \
         patch("agents.benchmark_agent._load_jd", return_value="JD text"), \
         patch("agents.benchmark_agent._SYNTHESIS_TIMEOUT", 0.01):
        percentile, sample_size = await _run_2afc_pipeline("User proxy", "SWE Intern")

    assert isinstance(percentile, int)
    assert sample_size == len(_SEED_COMPETITORS)
```

- [ ] **Step 2: Run test — confirm it FAILS**

```bash
cd backend && python3 -m pytest tests/test_benchmark_pipeline.py -v 2>&1 | head -20
```

Expected: `ImportError` or `AttributeError` since `synthesize_cohort` isn't imported in the agent yet and `_SYNTHESIS_TIMEOUT` doesn't exist.

- [ ] **Step 3: Update `agents/benchmark_agent.py`**

Replace the file's import block and `_run_2afc_pipeline` function. The full updated sections (leave all other code — `_load_jd`, `agent`, `handle_query`, etc. — unchanged):

**Change 1 — imports** (find and replace these two lines near the top):
```python
# OLD:
from app.services.elo import run_tournament, win_rate_to_percentile  # noqa: E402
from app.services.twoafc_judge import judge_pair  # noqa: E402

# NEW:
from app.services.elo import elo_update, rating_to_percentile  # noqa: E402
from app.services.resume_synthesizer import synthesize_cohort  # noqa: E402
from app.services.twoafc_judge import judge_pair  # noqa: E402
```

**Change 2 — add module-level constant** after the `_FALLBACK_JD` block:
```python
# Timeout in seconds for the cohort synthesis step.
_SYNTHESIS_TIMEOUT: float = 60.0
```

**Change 3 — replace `_run_2afc_pipeline`** (the entire function, lines ~124–145 in the original):
```python
async def _run_2afc_pipeline(user_resume_proxy: str, target: str) -> tuple[int, int]:
    """Run 2AFC vs. a JD-synthesized cohort; return (percentile, n_competitors).

    Synthesis and judging both run in parallel. Falls back to _SEED_COMPETITORS
    if synthesis times out or raises.
    """
    jd = _load_jd(target)

    try:
        competitors = await asyncio.wait_for(
            synthesize_cohort(jd, target),
            timeout=_SYNTHESIS_TIMEOUT,
        )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning("Cohort synthesis failed (%s); falling back to seed competitors", exc)
        competitors = _SEED_COMPETITORS

    judge_tasks = [
        judge_pair(resume_a=user_resume_proxy, resume_b=comp, jd=jd)
        for comp in competitors
    ]
    winners: list[str] = list(
        await asyncio.wait_for(asyncio.gather(*judge_tasks), timeout=90.0)
    )

    # ELO: user starts at 1000; each competitor also starts at 1000 (no prior history).
    user_rating = 1000.0
    competitor_ratings: list[float] = []
    for winner in winners:
        comp_rating = 1000.0
        user_rating, final_comp = elo_update(user_rating, comp_rating, winner)
        competitor_ratings.append(final_comp)

    percentile = rating_to_percentile(user_rating, competitor_ratings)
    return percentile, len(competitors)
```

- [ ] **Step 4: Run the pipeline tests — confirm they PASS**

```bash
cd backend && python3 -m pytest tests/test_benchmark_pipeline.py -v
```

Expected: 4 tests, all PASSED.

- [ ] **Step 5: Run full suite — no regressions**

```bash
cd backend && python3 -m pytest --tb=short -q 2>&1 | tail -5
```

Expected: all tests pass (previous count + 4 new pipeline tests + 9 synthesizer tests).

- [ ] **Step 6: Commit**

```bash
git add backend/agents/benchmark_agent.py backend/tests/test_benchmark_pipeline.py
git commit -m "feat(benchmark): use JD-synthesized cohort + proper ELO in 2AFC pipeline"
```

---

## Self-Review

**Spec coverage:**
- [x] Synthesize resumes via TokenRouter → `synthesize_resume` in Task 1
- [x] 2 strong + 4 average + 2 weak = 8 competitors → `synthesize_cohort` defaults in Task 1
- [x] Falls back when key absent or call fails → `_fallback_for_tier` in Task 1
- [x] 2AFC + ELO wired into benchmark agent → `_run_2afc_pipeline` in Task 2
- [x] `elo_update` + `rating_to_percentile` used (replacing `win_rate_to_percentile`) → Task 2 imports
- [x] Parallel judging via `asyncio.gather` → Task 2 `_run_2afc_pipeline`
- [x] Synthesis timeout fallback → `_SYNTHESIS_TIMEOUT` + try/except in Task 2
- [x] API contract not modified → `app/models/schemas.py` and `agents/messages.py` untouched
- [x] Tests for synthesizer → Task 1 (9 tests)
- [x] Tests for pipeline → Task 2 (4 tests)

**Placeholder scan:** None found.

**Type consistency:**
- `synthesize_cohort` → `list[str]` in Task 1 ✓, consumed as `list[str]` in Task 2 ✓
- `elo_update(float, float, str) -> tuple[float, float]` used in Task 2 matches `app/services/elo.py` ✓
- `rating_to_percentile(float, list[float]) -> int` used in Task 2 matches `app/services/elo.py` ✓
- `judge_pair(resume_a=str, resume_b=str, jd=str) -> str` unchanged ✓
