"""Fetch.ai benchmark uAgent — peer percentile vs. people who landed the target.

Runs as its own process, auto-registers on the Almanac, and answers one-shot
external queries from FastAPI via uagents.query(). Computes a readiness percentile
from a seeded distribution of scores of people who already secured the role/school
(MASTER.md §6). The percentile is independent of the score formula — it makes the
number relative and motivating, not abstract.

Run:  python agents/benchmark_agent.py
On startup it prints its agent1q... address — copy into BENCHMARK_AGENT_ADDRESS
in backend/.env.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# on_query is the correct decorator for the uagents.query() external-query bridge
# that FastAPI uses (on_rest is a separate REST-handler model). It is marked
# deprecated in 0.25.2 but still functional; silence the noisy warning.
warnings.filterwarnings("ignore", message="on_query is deprecated.*")

from uagents import Agent, Context  # noqa: E402

from agents.messages import BenchmarkRequest, BenchmarkResponse  # noqa: E402

# Seeded reference distribution: scores of people who landed comparable roles.
# For the demo this is a fixed, plausible cohort; can be enriched live via Sai.
# Sorted ascending so percentile is a simple rank lookup.
_REFERENCE_COHORT: list[int] = sorted(
    [
        42, 48, 51, 55, 58, 60, 61, 63, 64, 66,
        67, 68, 69, 70, 71, 72, 73, 74, 75, 76,
        77, 78, 79, 80, 81, 82, 83, 85, 88, 91,
    ]
)


def percentile_of(score: int) -> int:
    """Percent of the reference cohort the candidate is at or above.

    Pure: counts how many cohort members scored <= the candidate's score, as a
    percentage. Clamped to [0, 100].
    """
    if not _REFERENCE_COHORT:
        return 0
    at_or_below = sum(1 for s in _REFERENCE_COHORT if s <= score)
    pct = round(100 * at_or_below / len(_REFERENCE_COHORT))
    return max(0, min(100, pct))


agent = Agent(
    name="benchmark_agent",
    seed="hired_benchmark_agent_seed_phrase_change_me",
    port=8002,
    endpoint=["http://localhost:8002/submit"],
)


@agent.on_event("startup")
async def _startup(ctx: Context) -> None:
    ctx.logger.info(f"benchmark_agent address: {agent.address}")
    ctx.logger.info("Copy this into BENCHMARK_AGENT_ADDRESS in backend/.env")


@agent.on_query(model=BenchmarkRequest, replies={BenchmarkResponse})
async def handle_query(ctx: Context, sender: str, msg: BenchmarkRequest) -> None:
    """Return the candidate's readiness percentile + cohort size vs. the seeded cohort."""
    await ctx.send(
        sender,
        BenchmarkResponse(
            percentile=percentile_of(msg.score),
            sample_size=len(_REFERENCE_COHORT),
        ),
    )


if __name__ == "__main__":
    agent.run()
