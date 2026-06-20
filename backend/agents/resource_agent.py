"""Fetch.ai resource uAgent — curated FREE resources per skill gap.

Runs as its own process, auto-registers on the Almanac, and answers one-shot
external queries from the FastAPI backend via uagents.query(). Genuine uAgent
usage (on_query handler), not a disguised function call.

Run:  python agents/resource_agent.py
On startup it prints its agent1q... address — copy that into RESOURCE_AGENT_ADDRESS
in backend/.env.

Verified against uagents==0.25.2: Agent(...), @agent.on_query(model=, replies={...}),
ctx.send(sender, ...), agent.run().
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

# Allow `python agents/resource_agent.py` from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# on_query is the correct decorator for the uagents.query() external-query bridge
# that FastAPI uses (on_rest is a separate REST-handler model). It is marked
# deprecated in 0.25.2 but still functional; silence the noisy warning.
warnings.filterwarnings("ignore", message="on_query is deprecated.*")

from uagents import Agent, Context  # noqa: E402

from agents.messages import ResourceRequest, ResourceResponse  # noqa: E402

# Curated, FREE, first-gen/low-income-friendly resources, keyed by scoring
# category. Library / community-college / MOOC / apprenticeship oriented.
RESOURCE_DB: dict[str, list[str]] = {
    "skills_match": [
        "freeCodeCamp — full free curricula for in-demand tech skills (freecodecamp.org)",
        "Coursera & edX — audit most courses free; financial aid covers certificates",
        "Your local public library — free LinkedIn Learning + Gale courses with a library card",
        "Community college non-credit / continuing-ed certificates (low or no cost)",
        "Department of Labor Apprenticeship Finder — earn while you learn (apprenticeship.gov)",
    ],
    "quantified_achievements": [
        "Google's free 'Resume building' guides — how to write metric-driven bullets",
        "XYZ bullet formula: 'Accomplished X, measured by Y, by doing Z'",
        "Your campus/community career center — free resume reviews with quantified-impact feedback",
        "Handshake resume resources (free for students) — quantified-bullet examples by field",
    ],
    "experience": [
        "Volunteer & micro-internships: Parker Dewey, Catchafire (free, resume-building gigs)",
        "Open-source contribution for portfolios: Up For Grabs, Good First Issues",
        "Local nonprofits & mutual-aid orgs — project experience that counts on a resume",
        "Registered apprenticeships — paid, structured experience (apprenticeship.gov)",
    ],
    "education": [
        "Khan Academy — free foundational courses across subjects",
        "Community college — lowest-cost path to a credential; transfer agreements available",
        "Google Career Certificates — job-ready, low-cost, financial aid available",
        "CLEP exams — earn college credit cheaply by testing out",
    ],
    "clarity": [
        "Hemingway Editor (free, web) — flags wordy, unclear sentences",
        "Purdue OWL — free resume & professional-writing guides",
        "Career-center resume review (free) — a human read for clarity and structure",
        "Action-verb lists (free, e.g. MIT CAPD) — replace weak verbs with strong ones",
    ],
}

_DEFAULT = [
    "freeCodeCamp (freecodecamp.org) — free, self-paced learning",
    "Your local public library — free courses, books, and career help with a library card",
    "Community college continuing-education programs — low or no cost",
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
    """Return curated free resources for the requested gap category."""
    resources = RESOURCE_DB.get(msg.gap_category.strip().lower(), _DEFAULT)
    await ctx.send(sender, ResourceResponse(resources=resources))


if __name__ == "__main__":
    agent.run()
