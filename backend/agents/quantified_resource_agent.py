"""Fetch.ai quantified achievements resource uAgent.

Handles the "quantified_achievements" gap category: bullet-writing frameworks,
XYZ formula guides, and workshops for turning vague descriptions into
metric-driven impact statements.

Run standalone:  python agents/quantified_resource_agent.py
Or via Bureau:   python agents/bureau.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore", message="on_query is deprecated.*")

from uagents import Agent, Context  # noqa: E402

from agents.messages import ResourceItem, SkillResourceRequest, SkillResourceResponse  # noqa: E402

RESOURCES: list[dict[str, str]] = [
    {"name": "XYZ Bullet Formula (Google guide)",
     "url": "https://www.coursera.org/articles/how-to-write-a-resume",
     "description": "Accomplished [X], measured by [Y], by doing [Z] — the formula that turns vague bullets into proof."},
    {"name": "Handshake Résumé Resources",
     "url": "https://joinhandshake.com/blog/students/how-to-write-a-resume/",
     "description": "Free field-by-field examples of quantified bullets across industries."},
    {"name": "Purdue OWL — Quantifying Achievements",
     "url": "https://owl.purdue.edu/owl/job_search_writing/resumes_and_vitas/index.html",
     "description": "Free guide on turning responsibilities into measurable impact statements."},
    {"name": "Harvard OCS — Resume Action Words",
     "url": "https://hwpi.harvard.edu/files/ocs/files/hes-resume-cover-letter-guide.pdf",
     "description": "Free PDF guide on impact-oriented language and quantification strategies."},
]

agent = Agent(
    name="quantified_resource_agent",
    seed="hired_quantified_resource_agent_seed_v1",
    port=8007,
    endpoint=["http://localhost:8007/submit"],
)


@agent.on_event("startup")
async def _startup(ctx: Context) -> None:
    ctx.logger.info(f"quantified_resource_agent address: {agent.address}")
    ctx.logger.info("Copy into QUANTIFIED_RESOURCE_AGENT_ADDRESS in backend/.env")


@agent.on_message(model=SkillResourceRequest)
async def handle(ctx: Context, sender: str, msg: SkillResourceRequest) -> None:
    await ctx.send(
        sender,
        SkillResourceResponse(
            resources=[ResourceItem(**r) for r in RESOURCES],
            request_id=msg.request_id,
            skill=msg.skill,
        ),
    )


if __name__ == "__main__":
    agent.run()
