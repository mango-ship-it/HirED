"""POST /benchmark and POST /resources — bridged to the Fetch.ai uAgents.

The frontend has zero knowledge Fetch.ai is involved; it calls these REST
endpoints and the backend messages the agents via send_sync_message().

If an agent isn't running/configured, we return a graceful fallback so a live
demo never hard-fails on a cold agent (FRONTEND.md: "never depend on a cold API").
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

# Local fallback used only when the uAgent is unreachable, so the demo stays live.
_FALLBACK_RESOURCES = [
    "freeCodeCamp (freecodecamp.org) — free, self-paced learning",
    "Your local public library — free courses and career help with a library card",
    "Community college continuing-education programs — low or no cost",
]


@router.post("/benchmark", response_model=BenchmarkResponse)
async def benchmark(request: BenchmarkRequest) -> BenchmarkResponse:
    """Peer-readiness percentile from the Fetch.ai benchmark uAgent."""
    try:
        reply = await ask_agent(
            benchmark_agent_address(),
            AgentBenchmarkRequest(score=request.score, target=request.target),
            AgentBenchmarkResponse,
        )
        return BenchmarkResponse(percentile=int(reply.percentile))
    except (AgentUnavailableError, ValueError, AttributeError) as exc:
        # Deterministic local fallback so a cold agent never breaks the demo.
        logger.warning("benchmark agent unavailable, using fallback: %s", exc)
        fallback = max(0, min(100, request.score - 5))
        return BenchmarkResponse(percentile=fallback)


@router.post("/resources", response_model=ResourcesResponse)
async def resources(request: ResourcesRequest) -> ResourcesResponse:
    """Curated free resources for a gap, from the Fetch.ai resource uAgent."""
    try:
        reply = await ask_agent(
            resource_agent_address(),
            AgentResourceRequest(
                gap_category=request.gap_category, context=request.context
            ),
            AgentResourceResponse,
        )
        return ResourcesResponse(resources=list(reply.resources))
    except (AgentUnavailableError, ValueError, AttributeError) as exc:
        logger.warning("resource agent unavailable, using fallback: %s", exc)
        return ResourcesResponse(resources=_FALLBACK_RESOURCES)
