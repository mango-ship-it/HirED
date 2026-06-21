"""Build a detailed, domain-agnostic learning plan: real resources per skill gap.

Works for ANY field (chef, CDL/bus driver, fast food, software) using only the data we
have: the missing skills + the target role + optional location. Resources use REAL
search links (YouTube, web, maps) — never fabricated URLs — plus targeted practice
(LeetCode for coding roles), local "near you" options, and a credentials heads-up.
Free + deterministic (no API cost). HirED is a career *education* tool — this is the
"what to learn and where, for free" layer.
"""

from __future__ import annotations

from urllib.parse import quote_plus

# Subset of SKILL_VOCAB that signals a coding role (adds LeetCode practice).
_CODING_SKILLS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "ruby", "swift",
    "kotlin", "php", "scala", "sql", "react", "angular", "vue", "node.js",
}
_CODING_ROLE_WORDS = ("engineer", "developer", "programmer", "software", "data scientist", "ml ")


def is_coding_role(role: str, skills: list[str]) -> bool:
    text = (role + " " + " ".join(skills)).lower()
    if any(w in text for w in _CODING_ROLE_WORDS):
        return True
    return any(s.lower() in _CODING_SKILLS for s in skills)


def resources_for_skill(skill: str, *, location: str, coding: bool) -> list[dict]:
    cards = [
        {
            "title": f"{skill}: free video course",
            "type": "video",
            "url": f"https://www.youtube.com/results?search_query={quote_plus(skill + ' full course')}",
            "why": "Free, self-paced video lessons — pick a highly-viewed recent one.",
        },
        {
            "title": f"{skill}: online course",
            "type": "course",
            "url": f"https://www.coursera.org/search?query={quote_plus(skill)}",
            "why": "Audit most courses free; financial aid covers paid certificates.",
        },
    ]
    if location:
        cards.append({
            "title": f"{skill} training near {location}",
            "type": "local",
            "url": f"https://www.google.com/search?q={quote_plus(skill + ' training course near ' + location)}",
            "why": "In-person classes or schools close to you.",
            "near_you": True,
        })
    if coding:
        cards.append({
            "title": f"Practice {skill} on LeetCode",
            "type": "practice",
            "url": f"https://leetcode.com/problemset/?search={quote_plus(skill)}",
            "why": "Targeted problems to build interview-ready fluency.",
        })
    return cards


_CREDENTIAL_NOTE = (
    "Heads-up: some programs or certificates ask for a high-school diploma/GED or a "
    "prerequisite course — check entry requirements before enrolling (many free options "
    "have none)."
)


def _norm(card: dict) -> dict:
    """Normalize any resource card (Exa or deterministic) to {name, url, type, why, description}."""
    out = {
        "name": card.get("name") or card.get("title") or card.get("url"),
        "url": card.get("url"),
        "type": card.get("type"),
        "why": card.get("why"),
        "description": card.get("description") or card.get("snippet") or "",
    }
    if card.get("near_you"):
        out["near_you"] = True
    return out


def build_plan(
    skills: list[str],
    *,
    role: str = "",
    location: str = "",
    limit_skills: int = 6,
    company: str | None = None,
    leetcode_problems: list[dict] | None = None,
    resources_by_skill: dict[str, list[dict]] | None = None,
) -> dict:
    """A per-skill resource breakdown + role-level credentials/local options.

    When `leetcode_problems` are supplied (a coding role at a known company), the plan
    also includes a `company_practice` section of the exact problems that company asks.

    `resources_by_skill` is the integration seam for a real-resource provider (e.g. Exa
    search): if it has entries for a skill, those REAL ranked resources replace the
    deterministic search-link cards; otherwise we fall back to the search links. Each
    provided resource should be a card dict ({title, url, type, why}).
    """
    coding = is_coding_role(role, skills)
    provided = resources_by_skill or {}
    items = []
    for skill in skills[:limit_skills]:
        real = provided.get(skill) or provided.get(skill.lower())
        cards = real if real else resources_for_skill(skill, location=location, coding=coding)
        items.append({
            "skill": skill,
            "resources": [_norm(c) for c in cards],
            "credential_note": _CREDENTIAL_NOTE,
        })
    plan = {"role": role, "location": location, "is_coding": coding, "items": items}
    if leetcode_problems:
        plan["company_practice"] = {
            "company": company,
            "note": f"Most-asked LeetCode problems at {company} — start at the top (highest frequency).",
            "problems": leetcode_problems,
        }
    if role:
        plan["role_resources"] = [
            {
                "title": f"{role}: certifications & licenses needed",
                "type": "credential",
                "url": f"https://www.google.com/search?q={quote_plus(role + ' certification license requirements')}",
                "why": "What credentials this role typically requires, and how to earn them cheaply.",
            }
        ]
        if location:
            plan["role_resources"].append({
                "title": f"{role} schools/programs near {location}",
                "type": "local",
                "url": f"https://www.google.com/search?q={quote_plus(role + ' training program school near ' + location)}",
                "why": "Local, often low-cost training programs.",
                "near_you": True,
            })
        plan["role_resources"] = [_norm(c) for c in plan["role_resources"]]
    return plan
