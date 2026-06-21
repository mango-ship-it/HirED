"""2AFC (two-alternative forced choice) judging via TokenRouter.

TokenRouter is an OpenAI-compatible gateway for 300+ lightweight models.
We use it here to run many pairwise resume comparisons cheaply and in parallel.

Each call asks the model: "Given this JD, is candidate A or B stronger?"
The model returns JSON {"winner": "A"} or {"winner": "B"}.

Set TOKEN_ROUTER_API_KEY and optionally TOKEN_ROUTER_BASE_URL / TOKEN_ROUTER_MODEL
in backend/.env. Falls back to a simple heuristic (score comparison) if the key
is absent so the demo works without a TokenRouter account.
"""

from __future__ import annotations

import json
import logging
import re

from app.config import get_settings

logger = logging.getLogger("hired.twoafc")

_SYSTEM = (
    "You are an expert recruiter judging two candidates for a job. "
    "Given a job description and two resumes labelled A and B, pick which candidate "
    "is the stronger fit for this specific role. "
    "Consider skills match, quantified impact, relevant experience, education, and clarity. "
    'Return ONLY valid JSON with no explanation: {"winner": "A"} or {"winner": "B"}.'
)

_USER_TEMPLATE = (
    "JOB DESCRIPTION:\n{jd}\n\n"
    "--- CANDIDATE A ---\n{resume_a}\n\n"
    "--- CANDIDATE B ---\n{resume_b}\n\n"
    "Which candidate is stronger for this role?"
)


async def judge_pair(resume_a: str, resume_b: str, jd: str) -> str:
    """Return 'A' or 'B' — the stronger candidate for the given JD.

    Uses TokenRouter (OpenAI-compatible) if TOKEN_ROUTER_API_KEY is set;
    otherwise falls back to a heuristic (the longer, richer resume wins).
    """
    settings = get_settings()
    if not settings.token_router_api_key:
        logger.debug("TOKEN_ROUTER_API_KEY not set; using heuristic fallback")
        return _heuristic_winner(resume_a, resume_b)

    try:
        return await _llm_judge(resume_a, resume_b, jd, settings)
    except Exception as exc:
        logger.warning("TokenRouter judge failed (%s); using heuristic fallback", exc)
        return _heuristic_winner(resume_a, resume_b)


async def _llm_judge(resume_a: str, resume_b: str, jd: str, settings) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.token_router_api_key,
        base_url=settings.token_router_base_url,
    )
    response = await client.chat.completions.create(
        model=settings.token_router_model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(
                    jd=jd[:3000],
                    resume_a=resume_a[:2000],
                    resume_b=resume_b[:2000],
                ),
            },
        ],
        max_tokens=20,
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    return _parse_winner(raw)


def _parse_winner(raw: str) -> str:
    """Extract 'A' or 'B' from the model's JSON response; default to 'A'."""
    try:
        data = json.loads(raw)
        winner = str(data.get("winner", "A")).strip().upper()
        return winner if winner in ("A", "B") else "A"
    except json.JSONDecodeError:
        match = re.search(r'"winner"\s*:\s*"([AB])"', raw)
        return match.group(1) if match else "A"


def _heuristic_winner(resume_a: str, resume_b: str) -> str:
    """Naive fallback: longer resume (more content) wins."""
    return "A" if len(resume_a) >= len(resume_b) else "B"
