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
    Candidate,
    Match,
    Resource,
    ResourceContext,
    ResourcesRequest,
    ResourcesResponse,
)
from app.services.exa_search import find_candidates, has_exa, resources_for_gap
from app.services.fetch_bridge import (
    AgentUnavailableError,
    ask_agent,
    benchmark_agent_address,
    resource_agent_address,
)
from app.services.store import load_profile
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
    """How you compare. Tries the Fetch.ai 2AFC/ELO agent; otherwise builds a REAL-candidate
    comparison (Exa) with a transparency note — that's the 'How you compare' page."""
    role = request.target.value

    # 1. Fetch.ai 2AFC/ELO agent (synthetic competitors), if it's running.
    try:
        reply = await ask_agent(
            benchmark_agent_address(),
            AgentBenchmarkRequest(score=request.score, target=role),
            AgentBenchmarkResponse,
        )
        percentile = int(reply.percentile)
        matches = [
            Match(
                competitor_headline=m.competitor_headline,
                competitor_resume=m.competitor_resume,
                user_won=m.user_won,
            )
            for m in getattr(reply, "matches", [])
        ]
        return BenchmarkResponse(
            percentile=percentile, sample_size=int(reply.sample_size),
            message=_benchmark_message(percentile, role), matches=matches,
        )
    except (AgentUnavailableError, ValueError, AttributeError) as exc:
        logger.warning("benchmark agent unavailable, using real-candidate comparison: %s", exc)

    # 2. Real-candidate comparison via Exa — real professionals + a transparency note.
    percentile = max(1, min(99, request.score - 5))
    candidates: list[Candidate] = []
    if has_exa() and role:
        try:
            found = await find_candidates(role)
            candidates = [
                Candidate(name=c["name"], url=c["url"], why_stronger=c["why_stronger"]) for c in found
            ]
        except Exception:
            logger.exception("real-candidate comparison failed")
    transparency = (
        f"Your readiness score ({request.score}/100) is built from 5 weighted factors — skills "
        f"match (35%), quantified impact (25%), experience (20%), education (10%), and clarity "
        f"(10%) — so the number is fully reproducible. The percentile is an estimate from that "
        f"readiness score. The profiles below are real {role} professionals, shown so you can see "
        f"concretely what strong candidates bring and where to grow."
    )
    return BenchmarkResponse(
        percentile=percentile,
        sample_size=len(candidates) or _FALLBACK_SAMPLE_SIZE,
        message=_benchmark_message(percentile, role),
        matches=[],
        candidates=candidates,
        transparency=transparency,
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
    """Role-specific free resources. EXA FIRST — real, exact courses that work for ANY job —
    and we index every result so the Redis vector index grows into a knowledge base used as
    the fallback once it's rich. Order: Exa -> Redis index -> agent -> static."""
    role = _role(request.context)

    # Personalize the 'why it helps' to THIS user's resume (their actual skill gaps), when known.
    user_context = ""
    if request.user_id:
        record = await load_profile(request.user_id)
        if record:
            gaps = [g for g in (record.get("missing_skills") or []) if g][:3]
            if gaps:
                user_context = "still needs to build " + ", ".join(gaps)

    # 1. Exa FIRST — real, exact, role-specific resources for ANY job. Index the results
    #    (best-effort) so the Redis vector index keeps growing for the fallback below.
    if has_exa() and role:
        try:
            hits = await resources_for_gap(request.gap_category, role, user_context=user_context)
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

    # 2. Redis vector index — the GROWN knowledge base, used only when Exa is off/capped/failed.
    #    The distance threshold keeps it role-focused even as it accumulates many roles.
    indexed = await vector_search(
        f"{request.gap_category.replace('_', ' ')} for a {role}".strip(), k=4, max_distance=0.35
    )
    if indexed:
        return ResourcesResponse(
            resources=[Resource(name=h["name"], url=h["url"], description=h["description"]) for h in indexed]
        )

    # 3. Fetch.ai resource uAgent, then 4. static fallback.
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
