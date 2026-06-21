"""Dependency-free fallback extraction + lessons (no API key required).

Used when ANTHROPIC_API_KEY isn't configured (or Claude errors), so `/score`
returns real, contract-shaped data with ZERO external setup — the frontend works
end-to-end immediately. Rough but deterministic; Claude is preferred for quality
when a key is present.
"""

from __future__ import annotations

import re

from app.models.extraction import ExtractedProfile
from app.models.schemas import Lesson

# Modest skill vocabulary (display casing preserved; matched case-insensitively).
_SKILL_VOCAB = [
    "Python", "Java", "JavaScript", "TypeScript", "SQL", "React", "Node.js",
    "Django", "Flask", "FastAPI", "AWS", "GCP", "Azure", "Docker", "Kubernetes",
    "Git", "Airflow", "dbt", "Spark", "pandas", "PyTorch", "TensorFlow",
    "Machine Learning", "Data Analysis", "Excel", "Tableau", "Power BI", "Figma",
    "SEO", "Google Analytics", "A/B Testing", "Content Marketing", "Social Media",
    "Project Management", "Agile", "Scrum", "Salesforce", "HubSpot", "Copywriting",
    "Accounting", "Leadership", "Communication", "Public Speaking",
]

# Education keyword -> ladder key understood by profile_signals._EDUCATION_ALIASES.
_DEGREES: list[tuple[str, tuple[str, ...]]] = [
    ("doctorate", ("phd", "ph.d", "doctorate", "doctoral")),
    ("master", ("master", "m.s", "msc", "mba", "m.eng")),
    ("bachelor", ("bachelor", "b.s", "bsc", "b.a", "b.s.", "undergraduate")),
    ("associate", ("associate", "a.a", "a.s")),
    ("some", ("some college", "coursework", "certificate", "bootcamp")),
]

_ACTION_VERBS = {
    "led", "built", "grew", "cut", "reduced", "launched", "created", "drove",
    "increased", "managed", "designed", "improved", "shipped", "delivered",
    "owned", "developed", "automated", "scaled", "negotiated",
}


def _found(text_lower: str) -> list[str]:
    return [skill for skill in _SKILL_VOCAB if skill.lower() in text_lower]


def _education_level(resume_lower: str) -> str:
    for key, keywords in _DEGREES:
        if any(kw in resume_lower for kw in keywords):
            return key
    return "none"


def _clarity_proxy(resume: str) -> float:
    words = resume.split()
    if not words:
        return 0.3
    verbs = sum(1 for w in words if w.strip(".,;:").lower() in _ACTION_VERBS)
    density = verbs / max(len(words) / 30, 1)  # action verbs per ~30 words
    return max(0.2, min(1.0, 0.4 + 0.15 * density))


def extract_profile_heuristic(resume: str, target: str) -> ExtractedProfile:
    """Best-effort structured profile using only string heuristics (no LLM)."""
    resume_lower, target_lower = resume.lower(), target.lower()
    target_skills = _found(target_lower)
    resume_skills = _found(resume_lower)

    if target_skills:
        required = target_skills
    elif resume_skills:
        required = resume_skills  # vague target -> grade against the candidate's own skills
    else:
        required = ["Communication", "Project Management"]

    matched = [s for s in required if s.lower() in resume_lower]
    missing = [s for s in required if s.lower() not in resume_lower]

    quantified = min(len(re.findall(r"\b\d[\d,\.]*\s?%?\b", resume)), 20)
    year_hits = re.findall(r"(\d+)\+?\s*years?", resume_lower)
    years = float(max((int(x) for x in year_hits), default=0))

    return ExtractedProfile(
        required_skills=required,
        matched_skills=matched,
        missing_skills=missing,
        quantified_achievement_count=quantified,
        total_achievement_count=max(quantified, resume.count("\n")),
        years_experience=years,
        education_level=_education_level(resume_lower),
        clarity_signal=_clarity_proxy(resume),
        target_summary=target.strip()[:120],
    )


# Canned, kind-but-honest lessons per category (brand voice: reliable and kind).
_LESSON_TEMPLATES: dict[str, dict[str, str]] = {
    "skills_match": {
        "category": "skills_match",
        "principle": "Mirror the exact skills the posting names — those are the words recruiters search for.",
        "example": "Posting wants 'SQL'? If you've queried a database, say 'SQL' explicitly, not 'databases'.",
        "action": "List the top 5 skills in the posting and add the ones you truly have to your resume.",
    },
    "quantified_achievements": {
        "category": "quantified_achievements",
        "principle": "Recruiters skim for numbers — unquantified bullets get skipped.",
        "example": "Before: 'Helped grow social media.'  After: 'Grew Instagram 3x (1.2k->3.6k) in 4 months.'",
        "action": "Add a number (%, count, time, or $) to your two strongest bullets today.",
    },
    "experience": {
        "category": "experience",
        "principle": "Relevant projects count as experience — paid isn't the only kind that matters.",
        "example": "A volunteer dashboard or open-source fix shows the same skills as a job.",
        "action": "Add one project or volunteer role that demonstrates a skill the role needs.",
    },
    "education": {
        "category": "education",
        "principle": "A free certificate can stand in for a credential you don't have yet.",
        "example": "A Google Career Certificate signals job-ready skills without a degree.",
        "action": "Pick one free certificate aligned to your target and add it to a 'Learning' section.",
    },
    "clarity": {
        "category": "clarity",
        "principle": "Lead each bullet with a strong verb and a result, not 'Responsible for'.",
        "example": "Before: 'Responsible for reports.'  After: 'Built weekly reports that cut prep time 40%.'",
        "action": "Rewrite three bullets to start with an action verb and end with an outcome.",
    },
}


def heuristic_lessons(category_scores: dict[str, int]) -> list[Lesson]:
    """Templated lessons for the genuine gaps (a stronger resume yields fewer)."""
    from app.scoring import select_gaps

    weakest = select_gaps(category_scores)
    return [
        Lesson(**_LESSON_TEMPLATES[key])
        for key, _ in weakest
        if key in _LESSON_TEMPLATES
    ]
