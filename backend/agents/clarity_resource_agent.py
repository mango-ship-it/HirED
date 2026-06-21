"""Fetch.ai clarity resource uAgent — resume writing and communication resources.

Handles the "clarity" gap category: action verbs, readable structure,
concise writing tools, and professional writing guides.

Run standalone:  python agents/clarity_resource_agent.py
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
    {"name": "Hemingway Editor",
     "url": "https://hemingwayapp.com",
     "description": "Free web tool that highlights wordy, unclear sentences — paste your bullets, fix them instantly."},
    {"name": "Purdue OWL — Résumé Guide",
     "url": "https://owl.purdue.edu/owl/job_search_writing/resumes_and_vitas/index.html",
     "description": "Free, authoritative guide to résumé structure, phrasing, and professional writing."},
    {"name": "MIT CAPD — Action Verbs List",
     "url": "https://capd.mit.edu/resources/",
     "description": "Free list of strong, specific action verbs organized by skill type — swap weak verbs fast."},
    {"name": "Resume Worded",
     "url": "https://resumeworded.com",
     "description": "Free AI-powered résumé scorer that flags passive language and weak phrasing."},
]

agent = Agent(
    name="clarity_resource_agent",
    seed="hired_clarity_resource_agent_seed_v1",
    port=8006,
    endpoint=["http://localhost:8006/submit"],
)


@agent.on_event("startup")
async def _startup(ctx: Context) -> None:
    ctx.logger.info(f"clarity_resource_agent address: {agent.address}")
    ctx.logger.info("Copy into CLARITY_RESOURCE_AGENT_ADDRESS in backend/.env")


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
