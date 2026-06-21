"""Extract real in-demand skills from scraped job descriptions (JobSpy data in Redis).

Reinforces "readiness" with REAL employer demand: counts how many postings for a
target role mention each known skill, ranked by frequency, and compares against a
candidate's skills to show what the market wants that they have / lack.

Free + deterministic (keyword vocabulary over the JD text) — no API cost. Additive:
does NOT touch the deterministic score; it surfaces a separate "market demand" view.
"""

from __future__ import annotations

from app.data.skills import SKILL_VOCAB


def top_skills_from_jobs(jobs: list[dict], *, limit: int = 12) -> list[dict]:
    """Rank skills by how many postings mention them. count = # of postings (of N)."""
    if not jobs:
        return []
    texts = [f"{j.get('title', '')} {j.get('description', '')}".lower() for j in jobs]
    ranked: list[dict] = []
    for skill in SKILL_VOCAB:
        needle = skill.lower()
        mentions = sum(1 for t in texts if needle in t)
        if mentions:
            ranked.append({"skill": skill, "count": mentions})
    ranked.sort(key=lambda r: (-r["count"], r["skill"]))
    return ranked[:limit]


def compare_to_market(
    jobs: list[dict], candidate_skills: list[str], *, limit: int = 12
) -> dict:
    """Market skills for the role + which ones the candidate has / lacks."""
    market = top_skills_from_jobs(jobs, limit=limit)
    have = {s.strip().lower() for s in candidate_skills if s}
    return {
        "sample_size": len(jobs),
        "market_skills": market,
        "you_have": [m["skill"] for m in market if m["skill"].lower() in have],
        "you_lack": [m["skill"] for m in market if m["skill"].lower() not in have],
    }


def skills_in_text(text: str) -> list[str]:
    """Known skills present in arbitrary text (a resume, a JD)."""
    low = (text or "").lower()
    return [s for s in SKILL_VOCAB if s.lower() in low]


def jd_enriched_skills(resume_text: str, jobs: list[dict], *, limit: int = 15):
    """Recompute (required, matched, missing) from REAL job demand vs the resume.

    required = the skills most postings ask for; matched = those the resume shows;
    missing = the rest. This makes skills_match measure against what employers actually
    require, not a guess. Returns (required, matched, missing) — empty required if no JDs.
    """
    required = [r["skill"] for r in top_skills_from_jobs(jobs, limit=limit)]
    have = {s.lower() for s in skills_in_text(resume_text)}
    matched = [s for s in required if s.lower() in have]
    missing = [s for s in required if s.lower() not in have]
    return required, matched, missing
