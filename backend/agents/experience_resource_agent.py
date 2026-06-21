"""Fetch.ai experience resource uAgent — resources to build real-world experience.

Handles the "experience" gap category: micro-internships, volunteering,
open-source, freelance, and portfolio-building resources.

Run standalone:  python agents/experience_resource_agent.py
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
    {"name": "Parker Dewey — micro-internships",
     "url": "https://www.parkerdewey.com",
     "description": "Short, paid professional projects (5–40 hrs) that build real resume experience fast."},
    {"name": "Catchafire — skilled volunteering",
     "url": "https://www.catchafire.org",
     "description": "Apply your skills to nonprofit projects — counts as professional experience."},
    {"name": "Up For Grabs — open source",
     "url": "https://up-for-grabs.net",
     "description": "Curated beginner-friendly open-source issues across languages — free portfolio work."},
    {"name": "Idealist — volunteer + internships",
     "url": "https://www.idealist.org",
     "description": "Free board for social-impact internships and volunteer roles that count on a resume."},
    {"name": "All Star Code (for students)",
     "url": "https://www.allstarcode.org",
     "description": "Free summer internship program and tech community for underrepresented students."},
]

agent = Agent(
    name="experience_resource_agent",
    seed="hired_experience_resource_agent_seed_v1",
    port=8004,
    endpoint=["http://localhost:8004/submit"],
)


@agent.on_event("startup")
async def _startup(ctx: Context) -> None:
    ctx.logger.info(f"experience_resource_agent address: {agent.address}")
    ctx.logger.info("Copy into EXPERIENCE_RESOURCE_AGENT_ADDRESS in backend/.env")


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
