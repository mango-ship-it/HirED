"""Exa AI search — the CORE roadmap data source for HirED.

Builds DYNAMIC per-user queries (role + target/company + each MISSING skill + location)
and pulls real, current resources: courses, videos, practice problem sets, events,
networking communities, certifications, and scholarships — all aimed at closing the
user's missing skills. Works for ANY field (bus driver, chef, social worker, software):
the query strings are templated, never hardcoded per role.

Cost-guarded for a small (~$20) budget:
- `contents=False` so we never fetch/bill page text (title + url only) — ~$0.007/search.
- `num_results` capped at <=10 (base search price covers 10).
- every search cached in Redis 30 days (a repeated roadmap for the same role = $0).
- a hard per-process DAILY CALL CAP: once hit, searches short-circuit to [] and callers
  fall back to the free deterministic search links. This is the budget backstop.

Native async via AsyncExa. Verified against exa-py 2.14 (workflow wf_e4f33582).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone

from app.config import get_settings
from app.services.store import get_store

logger = logging.getLogger("hired.exa")

_NUM_RESULTS = 5
_CACHE_TTL = 30 * 24 * 3600
_client = None
_calls = {"date": "", "count": 0}  # process-wide daily counter (budget backstop)


def has_exa() -> bool:
    return bool(get_settings().exa_api_key)


def _get_client():
    global _client
    if _client is None:
        from exa_py import AsyncExa

        _client = AsyncExa(api_key=get_settings().exa_api_key)
    return _client


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _can_call() -> bool:
    if _calls["date"] != _today():
        _calls["date"], _calls["count"] = _today(), 0
    return _calls["count"] < get_settings().exa_daily_call_cap


# --- dynamic query templates (pure -> testable; never hardcoded per role) ---
def _course_query(skill: str, role: str) -> str:
    return f"Free or low-cost online course to learn {skill} for an aspiring {role}, beginner-friendly with a certificate:"


def _practice_query(skill: str, role: str) -> str:
    return f"Public practice problems, exercises, and problem sets to practice {skill} for a {role}:"


def _events_query(role: str, location: str, year: int) -> str:
    where = location or "the US"
    return f"Upcoming {year} conferences, meetups, and workshops for {role} professionals in {where}:"


def _networking_query(role: str) -> str:
    return (
        f"Professional associations, online communities, Slack and Discord groups, and "
        f"subreddits for {role}s to network and find mentorship:"
    )


def _certifications_query(role: str) -> str:
    return f"Official certifications, credentials, and licenses to work as a {role}, and how to earn them:"


def _scholarships_query(role: str) -> str:
    return (
        f"Scholarships, grants, and free-tuition financial aid for low-income and "
        f"first-generation people pursuing a career as a {role}:"
    )


# include_domains is a HARD filter in Exa. Restrict ONLY courses — coursera/udemy/
# youtube are reliably indexed and verified to return great results. For the discovery
# categories (events/networking/certs/scholarships) a hard filter over-filters to EMPTY
# (e.g. discord/linkedin are poorly indexed), so we let neural search find the best pages.
_COURSE_DOMAINS = ["coursera.org", "edx.org", "udemy.com", "khanacademy.org", "classcentral.com", "youtube.com"]


async def _search(
    query: str, *, card_type: str, why: str, include_domains: list[str] | None = None,
    num_results: int = _NUM_RESULTS, category: str | None = None,
) -> list[dict]:
    """One cached, cost-capped Exa search -> resource cards. [] on no-key/cap/failure."""
    if not has_exa():
        return []
    digest = hashlib.sha1(f"{query}|{include_domains}|{num_results}|{category}".encode()).hexdigest()[:16]
    cache_key = f"exa:{digest}"
    try:
        cached = await get_store().get_json(cache_key)
    except Exception:
        cached = None
    if cached is not None:
        return cached
    if not _can_call():
        logger.info("Exa daily call cap reached — falling back to search links")
        return []
    try:
        _calls["count"] += 1
        resp = await _get_client().search(
            query, type="auto", num_results=num_results,
            include_domains=include_domains, category=category, contents=False,
        )
    except Exception as exc:
        logger.info("Exa search failed (%s) — falling back", exc)
        return []
    cards = []
    for r in getattr(resp, "results", None) or []:
        url = getattr(r, "url", None)
        if not url:
            continue
        cards.append({"title": getattr(r, "title", None) or url, "url": url, "type": card_type, "why": why})
    try:
        await get_store().set_json(cache_key, cards, ttl=_CACHE_TTL)
    except Exception:
        pass
    return cards


# --- per-skill (closes a specific gap) ---
async def courses_for_skill(skill: str, role: str) -> list[dict]:
    return await _search(_course_query(skill, role), card_type="course",
                         why=f"Learn {skill}", include_domains=_COURSE_DOMAINS)


async def practice_for_skill(skill: str, role: str) -> list[dict]:
    return await _search(_practice_query(skill, role), card_type="practice", why=f"Practice {skill}")


# --- per-role (the broader roadmap) — no domain filter (neural search avoids empties) ---
async def events(role: str, location: str) -> list[dict]:
    year = datetime.now(timezone.utc).year
    return await _search(_events_query(role, location, year), card_type="event", why="Network in person")


async def networking(role: str) -> list[dict]:
    return await _search(_networking_query(role), card_type="community", why="Community & mentorship")


async def certifications(role: str) -> list[dict]:
    return await _search(_certifications_query(role), card_type="certification", why="Credential to earn")


async def scholarships(role: str) -> list[dict]:
    return await _search(_scholarships_query(role), card_type="scholarship", why="Funding to learn for free")


# Per-gap query templates — turn a scoring gap + the user's ROLE into a real,
# role-specific Exa search (so a golf coach gets golf resources, not freeCodeCamp).
_GAP_QUERY = {
    "skills_match": "free online courses and tutorials to learn the core skills needed to become a {role}",
    "quantified_achievements": "how to add numbers and measurable results to a {role} resume, with concrete examples",
    "experience": "free ways to gain real experience as a {role} — volunteering, apprenticeships, hands-on practice",
    "education": "free or low-cost certifications, licenses, and training to become a {role}",
    "clarity": "how to write a clear, strong {role} resume — free guides, templates, and examples",
}


async def resources_for_gap(gap_category: str, role: str) -> list[dict]:
    """Real, ROLE-SPECIFIC free resources to close a scoring gap (via Exa web search)."""
    template = _GAP_QUERY.get(gap_category, "free resources and courses to become a {role}")
    query = template.format(role=role or "this role")
    gap_phrase = gap_category.replace("_", " ")
    return await _search(query, card_type="resource", why=f"Free help with {gap_phrase} for a {role}")


async def people_to_connect(role: str, location: str = "") -> list[dict]:
    """Real people/mentors to connect with for the role (Exa 'people' category)."""
    where = f" in {location}" if location else ""
    return await _search(
        f"Profiles of {role} professionals, mentors, and industry leaders to learn from and connect with{where}:",
        card_type="person", why="Person to connect with", category="people",
    )


async def exa_resources_by_skill(skills: list[str], role: str, *, max_skills: int = 3) -> dict[str, list[dict]]:
    """Real course resources per skill for build_plan(resources_by_skill=...). <=max_skills searches."""
    if not has_exa() or not skills:
        return {}
    chosen = skills[:max_skills]
    found = await asyncio.gather(*(courses_for_skill(s, role) for s in chosen))
    return {skill: cards for skill, cards in zip(chosen, found) if cards}


async def full_roadmap(role: str, skills: list[str], location: str, *, max_skills: int = 3) -> dict | None:
    """Full multi-category roadmap. ~2*max_skills + 4 searches cold; cached 30d. None if no key."""
    if not has_exa():
        return None
    chosen = (skills or [])[:max_skills]
    per_skill_tasks = [
        asyncio.gather(courses_for_skill(s, role), practice_for_skill(s, role)) for s in chosen
    ]
    role_tasks = asyncio.gather(
        events(role, location), networking(role), certifications(role),
        scholarships(role), people_to_connect(role, location),
    )
    per_skill_results = await asyncio.gather(*per_skill_tasks) if per_skill_tasks else []
    events_r, networking_r, certs_r, schol_r, people_r = await role_tasks
    return {
        "role": role,
        "location": location,
        "skills": {
            skill: {"courses": courses, "practice": practice}
            for skill, (courses, practice) in zip(chosen, per_skill_results)
        },
        "events": events_r,
        "networking": networking_r,
        "people": people_r,
        "certifications": certs_r,
        "scholarships": schol_r,
    }


_STEP_TITLES = [
    ("certifications", "Earn a certification"),
    ("events", "Attend an event"),
    ("people", "Connect with people"),
    ("networking", "Join a community"),
    ("scholarships", "Fund your learning"),
]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "step"


def to_steps(data: dict) -> list[dict]:
    """Flatten the category-grouped roadmap into an ORDERED, reveal-friendly step list.

    Skills become the first learning steps (courses + practice merged), then the role
    milestones (certifications, events, people, community, scholarships). Each step gets
    an `order`, a stable `id`, and a `locked` flag (everything after step 1 starts locked)
    so the frontend can render an "unlock as you go" roadmap with zero extra logic.
    """
    steps: list[dict] = []
    for skill, res in (data.get("skills") or {}).items():
        resources = list(res.get("courses") or []) + list(res.get("practice") or [])
        steps.append({"kind": "skill", "skill": skill, "title": f"Learn {skill}", "resources": resources})
    for kind, title in _STEP_TITLES:
        items = data.get(kind) or []
        if items:
            steps.append({"kind": kind, "title": title, "resources": items})
    for i, step in enumerate(steps):
        step["order"] = i + 1
        step["id"] = f"{step['kind']}-{_slug(step.get('skill') or step['kind'])}-{i + 1}"
        step["locked"] = i > 0  # first step open; the rest unlock as the user progresses
    return steps
