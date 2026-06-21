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

from openai import AsyncOpenAI

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
