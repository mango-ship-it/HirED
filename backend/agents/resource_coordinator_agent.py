"""Fetch.ai resource coordinator uAgent.

Entry point for FastAPI's /resources route. Receives ResourceRequest (with
missing_skills: list[str]), fans out SkillResourceRequest messages to the
appropriate specialist agents, collects their replies via asyncio events, and
returns an aggregated ResourceResponse.

Routing logic:
  - gap_category == "skills_match" AND missing_skills non-empty
      → one SkillResourceRequest per skill to skills_resource_agent
  - gap_category == "experience"          → experience_resource_agent
  - gap_category == "education"           → education_resource_agent
  - gap_category == "clarity"             → clarity_resource_agent
  - gap_category == "quantified_achievements" → quantified_resource_agent
  - gap_category == "skills_match" with no missing_skills → skills_resource_agent ("general")
  - specialist timeout or address missing → static FALLBACK_DB for that category

Run standalone:  python agents/resource_coordinator_agent.py
Or via Bureau:   python agents/bureau.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore", message="on_query is deprecated.*")

from uagents import Agent, Context  # noqa: E402

from agents.messages import (  # noqa: E402
    ResourceItem,
    ResourceRequest,
    ResourceResponse,
    SkillResourceRequest,
    SkillResourceResponse,
)
from app.config import get_settings  # noqa: E402

logger = logging.getLogger("hired.resource_coordinator")

_SPECIALIST_TIMEOUT = 3.0  # seconds to wait for each specialist
_MAX_RESOURCES = 6         # cap on aggregated response

# Static fallback per category — used when a specialist is unreachable.
_FALLBACK: dict[str, list[dict[str, str]]] = {
    "skills_match": [
        {"name": "freeCodeCamp", "url": "https://www.freecodecamp.org",
         "description": "Free, self-paced learning across many in-demand tech tracks."},
        {"name": "Library LinkedIn Learning", "url": "https://www.linkedin.com/learning",
         "description": "Free with a public-library card — courses on hundreds of skills."},
    ],
    "experience": [
        {"name": "Parker Dewey micro-internships", "url": "https://www.parkerdewey.com",
         "description": "Short, paid projects that build real resume experience."},
        {"name": "Up For Grabs (open source)", "url": "https://up-for-grabs.net",
         "description": "Beginner-friendly open-source issues to build a portfolio."},
    ],
    "education": [
        {"name": "Google Career Certificates", "url": "https://grow.google/certificates/",
         "description": "Job-ready certificates — financial aid available."},
        {"name": "Khan Academy", "url": "https://www.khanacademy.org",
         "description": "Free foundational courses across most subjects."},
    ],
    "clarity": [
        {"name": "Hemingway Editor", "url": "https://hemingwayapp.com",
         "description": "Free tool that flags wordy sentences."},
        {"name": "Purdue OWL", "url": "https://owl.purdue.edu",
         "description": "Free résumé and professional-writing guides."},
    ],
    "quantified_achievements": [
        {"name": "XYZ bullet formula", "url": "https://www.coursera.org/articles/how-to-write-a-resume",
         "description": "Accomplished [X], measured by [Y], by doing [Z]."},
        {"name": "Handshake résumé guide", "url": "https://joinhandshake.com",
         "description": "Free field-by-field quantified-bullet examples."},
    ],
}

_DEFAULT_FALLBACK = [
    ResourceItem(name="freeCodeCamp", url="https://www.freecodecamp.org",
                 description="Free, self-paced learning across many tracks."),
    ResourceItem(name="Your public library", url="https://www.usa.gov/libraries",
                 description="Free courses and career help with a library card."),
]


# ---------------------------------------------------------------------------
# Pending request registry — keyed by request_id.
# Each entry: {"event": asyncio.Event, "results": list, "expected": int, "received": int}
# ---------------------------------------------------------------------------
_pending: dict[str, dict] = {}


def _specialist_address(gap_category: str) -> str:
    """Return the env-configured specialist address for a non-skills gap category."""
    s = get_settings()
    mapping = {
        "experience": getattr(s, "experience_resource_agent_address", ""),
        "education": getattr(s, "education_resource_agent_address", ""),
        "clarity": getattr(s, "clarity_resource_agent_address", ""),
        "quantified_achievements": getattr(s, "quantified_resource_agent_address", ""),
        "skills_match": getattr(s, "skills_resource_agent_address", ""),
    }
    return mapping.get(gap_category, "")


def _skills_agent_address() -> str:
    return getattr(get_settings(), "skills_resource_agent_address", "")


def _fallback_items(gap_category: str) -> list[ResourceItem]:
    rows = _FALLBACK.get(gap_category, [])
    return [ResourceItem(**r) for r in rows] or _DEFAULT_FALLBACK


def _dedupe(items: list[ResourceItem]) -> list[ResourceItem]:
    seen: set[str] = set()
    out: list[ResourceItem] = []
    for item in items:
        if item.url not in seen:
            seen.add(item.url)
            out.append(item)
    return out


agent = Agent(
    name="resource_coordinator_agent",
    seed="hired_resource_coordinator_agent_seed_v1",
    port=8001,
    endpoint=["http://localhost:8001/submit"],
)


@agent.on_event("startup")
async def _startup(ctx: Context) -> None:
    ctx.logger.info(f"resource_coordinator_agent address: {agent.address}")
    ctx.logger.info("Copy into RESOURCE_COORDINATOR_ADDRESS in backend/.env")


@agent.on_query(model=ResourceRequest, replies={ResourceResponse})
async def handle_query(ctx: Context, sender: str, msg: ResourceRequest) -> None:
    """Fan out to specialist agents, collect replies, return aggregated resources."""
    # Build the list of (address, skill) pairs to query.
    queries: list[tuple[str, str]] = []

    if msg.missing_skills and msg.gap_category == "skills_match":
        addr = _skills_agent_address()
        if addr:
            for skill in msg.missing_skills:
                queries.append((addr, skill))
        # else falls through to static fallback below
    else:
        addr = _specialist_address(msg.gap_category)
        if addr:
            queries.append((addr, msg.gap_category))

    if not queries:
        # No specialist configured — use static fallback immediately.
        await ctx.send(sender, ResourceResponse(resources=_fallback_items(msg.gap_category)))
        return

    request_id = str(uuid.uuid4())
    event = asyncio.Event()
    _pending[request_id] = {
        "event": event,
        "results": [],
        "expected": len(queries),
        "received": 0,
    }

    for addr, skill in queries:
        await ctx.send(addr, SkillResourceRequest(skill=skill, request_id=request_id))

    try:
        await asyncio.wait_for(event.wait(), timeout=_SPECIALIST_TIMEOUT)
    except asyncio.TimeoutError:
        ctx.logger.warning(
            "Specialist timeout for request %s (%d/%d received)",
            request_id,
            _pending.get(request_id, {}).get("received", 0),
            len(queries),
        )

    state = _pending.pop(request_id, {})
    results: list[ResourceItem] = state.get("results", [])

    if not results:
        results = _fallback_items(msg.gap_category)

    await ctx.send(
        sender,
        ResourceResponse(resources=_dedupe(results)[:_MAX_RESOURCES]),
    )


@agent.on_message(model=SkillResourceResponse)
async def handle_specialist_reply(ctx: Context, sender: str, msg: SkillResourceResponse) -> None:
    """Collect a specialist's reply and signal the waiting query handler when all arrive."""
    state = _pending.get(msg.request_id)
    if state is None:
        # Reply arrived after timeout — discard.
        return

    state["results"].extend(msg.resources)
    state["received"] += 1

    if state["received"] >= state["expected"]:
        state["event"].set()


if __name__ == "__main__":
    agent.run()
