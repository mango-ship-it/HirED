"""Fetch.ai education resource uAgent — free credentials and degree alternatives.

Handles the "education" gap category: free certifications, community college
pathways, CLEP exams, and government-backed education programs.

Run standalone:  python agents/education_resource_agent.py
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
    {"name": "Google Career Certificates",
     "url": "https://grow.google/certificates/",
     "description": "Job-ready certificates in IT, data, UX, and project management — financial aid available."},
    {"name": "Khan Academy",
     "url": "https://www.khanacademy.org",
     "description": "Free foundational courses from math to computing — pairs with community college prep."},
    {"name": "CLEP Exams",
     "url": "https://clep.collegeboard.org",
     "description": "Earn real college credits cheaply by testing out — recognized at 2,900+ institutions."},
    {"name": "Community College Finder",
     "url": "https://www.collegeboard.org/college-search/find-colleges",
     "description": "Find affordable community college programs — transferable credits and low tuition."},
    {"name": "IBM SkillsBuild (free)",
     "url": "https://skillsbuild.org",
     "description": "Free tech and business courses with IBM-backed credentials."},
    {"name": "Apprenticeship Finder (DOL)",
     "url": "https://www.apprenticeship.gov",
     "description": "Registered, paid apprenticeships — earn while you learn, often lead to full-time roles."},
]

agent = Agent(
    name="education_resource_agent",
    seed="hired_education_resource_agent_seed_v1",
    port=8005,
    endpoint=["http://localhost:8005/submit"],
)


@agent.on_event("startup")
async def _startup(ctx: Context) -> None:
    ctx.logger.info(f"education_resource_agent address: {agent.address}")
    ctx.logger.info("Copy into EDUCATION_RESOURCE_AGENT_ADDRESS in backend/.env")


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
