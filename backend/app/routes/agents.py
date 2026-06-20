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
    Resource,
    ResourcesRequest,
    ResourcesResponse,
)
from app.services.fetch_bridge import (
    AgentUnavailableError,
    ask_agent,
    benchmark_agent_address,
    resource_agent_address,
)

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
    try:
        reply = await ask_agent(
            benchmark_agent_address(),
            AgentBenchmarkRequest(score=request.score, target=request.target.value),
            AgentBenchmarkResponse,
        )
        percentile, sample_size = int(reply.percentile), int(reply.sample_size)
    except (AgentUnavailableError, ValueError, AttributeError) as exc:
        # Deterministic local fallback so a cold agent never breaks the demo.
        logger.warning("benchmark agent unavailable, using fallback: %s", exc)
        percentile = max(0, min(100, request.score - 5))
        sample_size = _FALLBACK_SAMPLE_SIZE
    return BenchmarkResponse(
        percentile=percentile,
        sample_size=sample_size,
        message=_benchmark_message(percentile, request.target.value),
    )


@router.post("/resources", response_model=ResourcesResponse)
async def resources(request: ResourcesRequest) -> ResourcesResponse:
    """Curated free resources for a gap, from the Fetch.ai resource uAgent."""
    context_hint = (
        f"first_gen={request.context.first_gen}; target_type={request.context.target_type}"
    )
    try:
        reply = await ask_agent(
            resource_agent_address(),
            AgentResourceRequest(gap_category=request.gap_category, context=context_hint),
            AgentResourceResponse,
        )
        items = [
            Resource(name=item.name, url=item.url, description=item.description)
            for item in reply.resources
        ]
        return ResourcesResponse(resources=items)
    except (AgentUnavailableError, ValueError, AttributeError) as exc:
        logger.warning("resource agent unavailable, using fallback: %s", exc)
        return ResourcesResponse(resources=_FALLBACK_RESOURCES)
