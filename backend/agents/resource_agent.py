"""Fetch.ai resource uAgent — curated FREE resources per skill gap.

Runs as its own process, auto-registers on the Almanac, and answers one-shot
external queries from FastAPI via send_sync_message. Genuine uAgent usage
(@on_query handler), not a disguised function call.

Run:  python agents/resource_agent.py
On startup it prints its agent1q... address — copy that into RESOURCE_AGENT_ADDRESS
in backend/.env.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

# Allow `python agents/resource_agent.py` from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# on_query is the correct decorator for the external-query bridge FastAPI uses.
# It is marked deprecated in 0.25.2 but still functional; silence the noisy warning.
warnings.filterwarnings("ignore", message="on_query is deprecated.*")

from uagents import Agent, Context  # noqa: E402

from agents.messages import ResourceItem, ResourceRequest, ResourceResponse  # noqa: E402

# Curated, FREE, first-gen / low-income-friendly resources, keyed by scoring
# category. Library / community-college / MOOC / apprenticeship oriented.
RESOURCE_DB: dict[str, list[dict[str, str]]] = {
    "skills_match": [
        {"name": "freeCodeCamp", "url": "https://www.freecodecamp.org",
         "description": "Free, full curricula for in-demand tech skills."},
        {"name": "Coursera (audit mode)", "url": "https://www.coursera.org",
         "description": "Audit most courses free; financial aid covers paid certificates."},
        {"name": "Apprenticeship Finder (DOL)", "url": "https://www.apprenticeship.gov",
         "description": "Earn while you learn — registered, paid apprenticeships."},
        {"name": "Library LinkedIn Learning", "url": "https://www.linkedin.com/learning",
         "description": "Free with a public-library card at most U.S. libraries."},
    ],
    "quantified_achievements": [
        {"name": "XYZ bullet formula", "url": "https://www.coursera.org/articles/how-to-write-a-resume",
         "description": "Write metric-driven bullets: 'Accomplished X, measured by Y, by doing Z.'"},
        {"name": "Purdue OWL résumé guide", "url": "https://owl.purdue.edu/owl/job_search_writing/resumes_and_vitas/index.html",
         "description": "Free guidance on quantifying impact and strong phrasing."},
        {"name": "Handshake résumé resources", "url": "https://joinhandshake.com",
         "description": "Free for students — quantified-bullet examples by field."},
    ],
    "experience": [
        {"name": "Parker Dewey micro-internships", "url": "https://www.parkerdewey.com",
         "description": "Short, paid projects that build real resume experience."},
        {"name": "Catchafire", "url": "https://www.catchafire.org",
         "description": "Skilled volunteer projects for nonprofits — counts as experience."},
        {"name": "Up For Grabs (open source)", "url": "https://up-for-grabs.net",
         "description": "Beginner-friendly open-source issues to build a portfolio."},
    ],
    "education": [
        {"name": "Khan Academy", "url": "https://www.khanacademy.org",
         "description": "Free foundational courses across most subjects."},
        {"name": "Google Career Certificates", "url": "https://grow.google/certificates",
         "description": "Job-ready, low-cost credentials; financial aid available."},
        {"name": "CLEP exams", "url": "https://clep.collegeboard.org",
         "description": "Earn real college credit cheaply by testing out."},
    ],
    "clarity": [
        {"name": "Hemingway Editor", "url": "https://hemingwayapp.com",
         "description": "Free web tool that flags wordy, unclear sentences."},
        {"name": "Purdue OWL", "url": "https://owl.purdue.edu",
         "description": "Free résumé and professional-writing guides."},
        {"name": "MIT CAPD action verbs", "url": "https://capd.mit.edu/resources/",
         "description": "Swap weak verbs for strong, specific ones."},
    ],
}

_DEFAULT: list[dict[str, str]] = [
    {"name": "freeCodeCamp", "url": "https://www.freecodecamp.org",
     "description": "Free, self-paced learning across many tracks."},
    {"name": "Your public library", "url": "https://www.usa.gov/libraries",
     "description": "Free courses, books, and career help with a library card."},
    {"name": "CareerOneStop", "url": "https://www.careeronestop.org",
     "description": "Free, government-run training finder and career tools."},
]

agent = Agent(
    name="resource_agent",
    seed="hired_resource_agent_seed_phrase_change_me",
    port=8001,
    endpoint=["http://localhost:8001/submit"],
)


@agent.on_event("startup")
async def _startup(ctx: Context) -> None:
    ctx.logger.info(f"resource_agent address: {agent.address}")
    ctx.logger.info("Copy this into RESOURCE_AGENT_ADDRESS in backend/.env")


@agent.on_query(model=ResourceRequest, replies={ResourceResponse})
async def handle_query(ctx: Context, sender: str, msg: ResourceRequest) -> None:
    """Return curated free resources (name/url/description) for the requested gap."""
    rows = RESOURCE_DB.get(msg.gap_category.strip().lower(), _DEFAULT)
    resources = [ResourceItem(**row) for row in rows]
    await ctx.send(sender, ResourceResponse(resources=resources))


if __name__ == "__main__":
    agent.run()
