"""Curated FREE, first-gen/low-income-friendly resource corpus.

Plain data (no deps) so both the Fetch.ai resource agent and the RedisVL semantic
search can use it. Each item is tagged with the scoring gap_category it helps.
"""

from __future__ import annotations

RESOURCE_CORPUS: list[dict[str, str]] = [
    # --- skills_match ---
    {"gap_category": "skills_match", "name": "freeCodeCamp",
     "url": "https://www.freecodecamp.org",
     "description": "Free, full curricula for in-demand technical skills."},
    {"gap_category": "skills_match", "name": "Coursera (audit mode)",
     "url": "https://www.coursera.org",
     "description": "Audit most courses free; financial aid covers paid certificates."},
    {"gap_category": "skills_match", "name": "Apprenticeship Finder (DOL)",
     "url": "https://www.apprenticeship.gov",
     "description": "Earn while you learn — registered, paid apprenticeships."},
    {"gap_category": "skills_match", "name": "Library LinkedIn Learning",
     "url": "https://www.linkedin.com/learning",
     "description": "Thousands of skill courses, free with a public-library card."},
    # --- quantified_achievements ---
    {"gap_category": "quantified_achievements", "name": "XYZ bullet formula",
     "url": "https://www.coursera.org/articles/how-to-write-a-resume",
     "description": "Write metric-driven resume bullets: accomplished X measured by Y by doing Z."},
    {"gap_category": "quantified_achievements", "name": "Purdue OWL resume guide",
     "url": "https://owl.purdue.edu/owl/job_search_writing/resumes_and_vitas/index.html",
     "description": "Free guidance on quantifying impact and strong action phrasing."},
    {"gap_category": "quantified_achievements", "name": "Handshake resume resources",
     "url": "https://joinhandshake.com",
     "description": "Free for students — quantified-bullet examples by field and role."},
    # --- experience ---
    {"gap_category": "experience", "name": "Parker Dewey micro-internships",
     "url": "https://www.parkerdewey.com",
     "description": "Short, paid projects that build real, resume-worthy experience."},
    {"gap_category": "experience", "name": "Catchafire",
     "url": "https://www.catchafire.org",
     "description": "Skilled volunteer projects for nonprofits that count as experience."},
    {"gap_category": "experience", "name": "Up For Grabs (open source)",
     "url": "https://up-for-grabs.net",
     "description": "Beginner-friendly open-source issues to build a project portfolio."},
    # --- education ---
    {"gap_category": "education", "name": "Khan Academy",
     "url": "https://www.khanacademy.org",
     "description": "Free foundational courses across most subjects."},
    {"gap_category": "education", "name": "Google Career Certificates",
     "url": "https://grow.google/certificates",
     "description": "Job-ready, low-cost credentials with financial aid available."},
    {"gap_category": "education", "name": "CLEP exams",
     "url": "https://clep.collegeboard.org",
     "description": "Earn real college credit cheaply by testing out of subjects."},
    # --- clarity ---
    {"gap_category": "clarity", "name": "Hemingway Editor",
     "url": "https://hemingwayapp.com",
     "description": "Free web tool that flags wordy, unclear sentences in your writing."},
    {"gap_category": "clarity", "name": "Purdue OWL writing lab",
     "url": "https://owl.purdue.edu",
     "description": "Free resume and professional-writing guides for clarity and structure."},
    {"gap_category": "clarity", "name": "MIT CAPD action verbs",
     "url": "https://capd.mit.edu/resources/",
     "description": "Swap weak verbs for strong, specific ones that read clearly."},
]


def corpus_for(gap_category: str) -> list[dict[str, str]]:
    """Static-fallback helper: resources tagged with a gap category (or all)."""
    matches = [r for r in RESOURCE_CORPUS if r["gap_category"] == gap_category]
    return matches or RESOURCE_CORPUS[:3]
