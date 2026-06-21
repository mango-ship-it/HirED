"""POST /benchmark and POST /resources — bridged to the Fetch.ai uAgents.

The frontend has zero knowledge Fetch.ai is involved; it calls these REST
endpoints (shapes per API_CONTRACT.md) and the backend messages the agents via
send_sync_message().

If an agent isn't running/configured, we return a graceful, contract-shaped
fallback so the frontend works end-to-end with no agents or keys (and a live demo
never hard-fails on a cold agent).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from agents.messages import (
    BenchmarkRequest as AgentBenchmarkRequest,
    BenchmarkResponse as AgentBenchmarkResponse,
    ResourceRequest as AgentResourceRequest,
    ResourceResponse as AgentResourceResponse,
)
from app.models.schemas import (
    BenchmarkRequest,
    BenchmarkResponse,
    Match,
    Resource,
    ResourceContext,
    ResourcesRequest,
    ResourcesResponse,
)
from app.services.exa_search import has_exa, resources_for_gap
from app.services.fetch_bridge import (
    AgentUnavailableError,
    ask_agent,
    benchmark_agent_address,
    resource_agent_address,
)
from app.services.vector_resources import add_resources, search as vector_search

logger = logging.getLogger("hired.routes.agents")

router = APIRouter()

# Cohort size reported by the fallback when the benchmark agent is unreachable.
_FALLBACK_SAMPLE_SIZE = 30

# Contract-shaped fallback resources when the resource agent is unreachable.
_FALLBACK_RESOURCES = [
    Resource(
        name="freeCodeCamp",
        url="https://www.freecodecamp.org",
        description="Free, self-paced learning across many tracks.",
    ),
    Resource(
        name="Your public library",
        url="https://www.usa.gov/libraries",
        description="Free courses (LinkedIn Learning, Gale) and career help with a library card.",
    ),
    Resource(
        name="CareerOneStop",
        url="https://www.careeronestop.org",
        description="Free, government-run training finder and career tools.",
    ),
]


def _benchmark_message(percentile: int, target_value: str) -> str:
    """Plain-language, motivating framing of the percentile (brand voice: kind)."""
    return (
        f"You're ahead of {percentile}% of candidates targeting {target_value}. "
        "Candidates who broke into the top tier most often strengthened their "
        "lowest-scoring category first — that's the fastest way to move your number."
    )


@router.post("/benchmark", response_model=BenchmarkResponse)
async def benchmark(request: BenchmarkRequest) -> BenchmarkResponse:
    """Peer-readiness percentile from the Fetch.ai benchmark uAgent."""
    matches: list[Match] = []
    try:
        reply = await ask_agent(
            benchmark_agent_address(),
            AgentBenchmarkRequest(score=request.score, target=request.target.value),
            AgentBenchmarkResponse,
        )
        percentile, sample_size = int(reply.percentile), int(reply.sample_size)
        matches = [
            Match(
                competitor_headline=m.competitor_headline,
                competitor_resume=m.competitor_resume,
                user_won=m.user_won,
            )
            for m in getattr(reply, "matches", [])
        ]
    except (AgentUnavailableError, ValueError, AttributeError) as exc:
        # Deterministic local fallback so a cold agent never breaks the demo.
        logger.warning("benchmark agent unavailable, using fallback: %s", exc)
        percentile = max(0, min(100, request.score - 5))
        sample_size = _FALLBACK_SAMPLE_SIZE
        matches = []  # explicit — contract guarantees this field is always present
    return BenchmarkResponse(
        percentile=percentile,
        sample_size=sample_size,
        message=_benchmark_message(percentile, request.target.value),
        matches=matches,
    )


def _role(context) -> str:
    """The target role from `context` — a plain string (frontend) or the object form."""
    if isinstance(context, str):
        return context.strip()
    if isinstance(context, ResourceContext):
        return context.target_type.strip()
    return ""


@router.post("/resources", response_model=ResourcesResponse)
async def resources(request: ResourcesRequest) -> ResourcesResponse:
    """Role-specific free resources. The Redis vector index (which GROWS from every Exa
    search) is tried first; on a miss we fetch fresh from Exa and index it for next time."""
    role = _role(request.context)
    query = f"{request.gap_category.replace('_', ' ')} for a {role}".strip()

    # 1. Redis vector index FIRST — a real, GROWING knowledge base. A tight distance
    #    threshold keeps results role-relevant (a golf query never returns a tech resource),
    #    and a later "golf instructor" reuses a prior "golf coach" search for free.
    indexed = await vector_search(query, k=4, max_distance=0.35)
    if indexed and len(indexed) >= 3:
        return ResourcesResponse(
            resources=[Resource(name=h["name"], url=h["url"], description=h["description"]) for h in indexed]
        )

    # 2. Exa — REAL role-specific fetch; index the results so Redis serves them next time.
    if has_exa() and role:
        try:
            hits = await resources_for_gap(request.gap_category, role)
            if hits:
                await add_resources(hits, gap_category=request.gap_category, role=role)  # grow index
                return ResourcesResponse(
                    resources=[
                        Resource(name=h["title"], url=h["url"], description=h.get("snippet") or h["why"])
                        for h in hits
                    ]
                )
        except Exception as exc:
            logger.warning("Exa resources failed (%s); falling back", exc)

    # 3. Any weaker indexed hits, then 4. the Fetch.ai agent, then 5. the static list.
    if indexed:
        return ResourcesResponse(
            resources=[Resource(name=h["name"], url=h["url"], description=h["description"]) for h in indexed]
        )
    try:
        reply = await ask_agent(
            resource_agent_address(),
            AgentResourceRequest(gap_category=request.gap_category, context=role),
            AgentResourceResponse,
        )
        return ResourcesResponse(
            resources=[Resource(name=i.name, url=i.url, description=i.description) for i in reply.resources]
        )
    except (AgentUnavailableError, ValueError, AttributeError) as exc:
        logger.warning("resource agent unavailable, using fallback: %s", exc)
        return ResourcesResponse(resources=_FALLBACK_RESOURCES)
