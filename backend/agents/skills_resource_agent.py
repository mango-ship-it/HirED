"""Fetch.ai skills resource uAgent — free learning resources keyed by skill name.

Receives SkillResourceRequest from the coordinator, returns resources for that
specific named skill (React, SQL, Python, etc.). Acts as the catch-all for any
skill not covered by the other specialist agents.

Run standalone:  python agents/skills_resource_agent.py
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

# Skill-level resource DB. Each key is a lowercase normalized skill name.
# 2-3 free resources per skill; prefer library/MOOC/official docs over paid.
SKILL_DB: dict[str, list[dict[str, str]]] = {
    "python": [
        {"name": "Python.org Tutorial", "url": "https://docs.python.org/3/tutorial/",
         "description": "The official free Python tutorial — from basics to standard library."},
        {"name": "freeCodeCamp Scientific Computing with Python",
         "url": "https://www.freecodecamp.org/learn/scientific-computing-with-python/",
         "description": "Free, project-based Python certification."},
    ],
    "javascript": [
        {"name": "The Odin Project — JavaScript", "url": "https://www.theodinproject.com/paths/full-stack-javascript",
         "description": "Free, project-driven full-stack JavaScript curriculum."},
        {"name": "javascript.info", "url": "https://javascript.info",
         "description": "Modern, thorough JS guide — free and ad-supported."},
    ],
    "typescript": [
        {"name": "TypeScript Handbook", "url": "https://www.typescriptlang.org/docs/handbook/intro.html",
         "description": "Official free TypeScript documentation and guide."},
        {"name": "Total TypeScript (free modules)", "url": "https://www.totaltypescript.com/tutorials",
         "description": "Free interactive TypeScript tutorials by Matt Pocock."},
    ],
    "react": [
        {"name": "React Docs (react.dev)", "url": "https://react.dev/learn",
         "description": "Official interactive React tutorial — free."},
        {"name": "freeCodeCamp Front End Libraries", "url": "https://www.freecodecamp.org/learn/front-end-development-libraries/",
         "description": "Free React + Redux certification with hands-on projects."},
    ],
    "node.js": [
        {"name": "Node.js Official Guides", "url": "https://nodejs.org/en/docs/guides",
         "description": "Official Node.js guides, free."},
        {"name": "The Odin Project — NodeJS", "url": "https://www.theodinproject.com/paths/full-stack-javascript/courses/nodejs",
         "description": "Free project-based Node.js course."},
    ],
    "sql": [
        {"name": "SQLZoo", "url": "https://sqlzoo.net",
         "description": "Free interactive SQL exercises in the browser — no setup."},
        {"name": "Mode SQL Tutorial", "url": "https://mode.com/sql-tutorial/",
         "description": "Free SQL tutorial from basics to advanced analytics."},
    ],
    "java": [
        {"name": "CS106A (Stanford) — free materials", "url": "https://web.stanford.edu/class/cs106a/",
         "description": "Stanford intro programming course materials — free to self-study."},
        {"name": "Codecademy Learn Java (free tier)", "url": "https://www.codecademy.com/learn/learn-java",
         "description": "Free introductory Java course with in-browser environment."},
    ],
    "c++": [
        {"name": "learncpp.com", "url": "https://www.learncpp.com",
         "description": "Comprehensive, free C++ tutorial from beginner to advanced."},
    ],
    "docker": [
        {"name": "Docker Getting Started", "url": "https://docs.docker.com/get-started/",
         "description": "Official Docker tutorial — free."},
        {"name": "Play with Docker", "url": "https://labs.play-with-docker.com",
         "description": "Free browser-based Docker lab — no install needed."},
    ],
    "kubernetes": [
        {"name": "Kubernetes Basics (official)", "url": "https://kubernetes.io/docs/tutorials/kubernetes-basics/",
         "description": "Official interactive Kubernetes tutorial — free."},
        {"name": "Killer.sh free tier", "url": "https://killer.sh",
         "description": "Free CKA/CKAD practice simulator (limited free sessions)."},
    ],
    "aws": [
        {"name": "AWS Skill Builder (free tier)", "url": "https://skillbuilder.aws",
         "description": "Free AWS training — 500+ courses including certification paths."},
        {"name": "Cloud Quest: Cloud Practitioner (free)", "url": "https://aws.amazon.com/training/digital/aws-cloud-quest/",
         "description": "Free gamified AWS fundamentals course."},
    ],
    "git": [
        {"name": "Git — the official book", "url": "https://git-scm.com/book/en/v2",
         "description": "Pro Git book — free online, covers everything."},
        {"name": "Learn Git Branching", "url": "https://learngitbranching.js.org",
         "description": "Free, visual, interactive Git tutorial in the browser."},
    ],
    "machine learning": [
        {"name": "fast.ai — Practical Deep Learning", "url": "https://course.fast.ai",
         "description": "Free, top-down ML course — start building on day 1."},
        {"name": "Google ML Crash Course", "url": "https://developers.google.com/machine-learning/crash-course",
         "description": "Free ML fundamentals with TensorFlow exercises."},
    ],
    "data science": [
        {"name": "Kaggle Learn", "url": "https://www.kaggle.com/learn",
         "description": "Free data science micro-courses with notebooks."},
        {"name": "freeCodeCamp Data Analysis with Python",
         "url": "https://www.freecodecamp.org/learn/data-analysis-with-python/",
         "description": "Free data analysis certification with pandas + NumPy projects."},
    ],
    "data analysis": [
        {"name": "Kaggle Learn — Pandas", "url": "https://www.kaggle.com/learn/pandas",
         "description": "Free hands-on pandas tutorial for data analysis."},
        {"name": "Google Data Analytics Certificate (audit)", "url": "https://www.coursera.org/professional-certificates/google-data-analytics",
         "description": "Audit most modules free on Coursera; financial aid available."},
    ],
    "communication": [
        {"name": "Coursera — Successful Negotiation (audit)", "url": "https://www.coursera.org/learn/negotiation-skills",
         "description": "Audit free; covers written and verbal professional communication."},
        {"name": "Toastmasters (free guest visits)", "url": "https://www.toastmasters.org/find-a-club",
         "description": "Visit any club as a guest free — great for spoken communication practice."},
    ],
    "leadership": [
        {"name": "Coursera — Inspiring and Motivating Individuals (audit)", "url": "https://www.coursera.org/learn/motivate-people-teams",
         "description": "Audit free; Michigan leadership fundamentals."},
    ],
    "project management": [
        {"name": "Google Project Management Certificate (audit)", "url": "https://www.coursera.org/professional-certificates/google-project-management",
         "description": "Audit most modules free on Coursera."},
        {"name": "PMI free resources", "url": "https://www.pmi.org/learning/library",
         "description": "Free webinars, templates, and articles from the project management institute."},
    ],
    "excel": [
        {"name": "Microsoft Excel training (free)", "url": "https://support.microsoft.com/en-us/office/excel-video-training-9bc05390-e94c-46af-a5b3-d7c22f6990bb",
         "description": "Free official Excel video training from Microsoft."},
        {"name": "Chandoo.org", "url": "https://chandoo.org/wp/learn-excel/",
         "description": "Free Excel tutorials from beginner to advanced."},
    ],
    "linux": [
        {"name": "Linux Journey", "url": "https://linuxjourney.com",
         "description": "Free, interactive Linux tutorial for beginners."},
        {"name": "The Linux Command Line (free book)", "url": "https://linuxcommand.org/tlcl.php",
         "description": "Free PDF/web book covering the Linux command line."},
    ],
}

# Normalize variations (aliases map to canonical keys)
_ALIASES: dict[str, str] = {
    "nodejs": "node.js", "node": "node.js",
    "js": "javascript", "es6": "javascript",
    "ts": "typescript",
    "ml": "machine learning", "deep learning": "machine learning",
    "dl": "machine learning",
    "k8s": "kubernetes",
    "bash": "linux", "shell": "linux", "shell scripting": "linux",
    "spreadsheets": "excel",
    "pm": "project management", "agile": "project management", "scrum": "project management",
    "public speaking": "communication", "writing": "communication",
}

_DEFAULT: list[dict[str, str]] = [
    {"name": "freeCodeCamp", "url": "https://www.freecodecamp.org",
     "description": "Free, self-paced learning across many in-demand tech tracks."},
    {"name": "Library LinkedIn Learning", "url": "https://www.linkedin.com/learning",
     "description": "Free with a public-library card — courses on hundreds of skills."},
    {"name": "Coursera (audit mode)", "url": "https://www.coursera.org",
     "description": "Audit most courses free; financial aid covers paid certificates."},
]


def _lookup(skill: str) -> list[dict[str, str]]:
    key = skill.strip().lower()
    key = _ALIASES.get(key, key)
    return SKILL_DB.get(key, _DEFAULT)


agent = Agent(
    name="skills_resource_agent",
    seed="hired_skills_resource_agent_seed_v1",
    port=8003,
    endpoint=["http://localhost:8003/submit"],
)


@agent.on_event("startup")
async def _startup(ctx: Context) -> None:
    ctx.logger.info(f"skills_resource_agent address: {agent.address}")
    ctx.logger.info("Copy into SKILLS_RESOURCE_AGENT_ADDRESS in backend/.env")


@agent.on_message(model=SkillResourceRequest)
async def handle(ctx: Context, sender: str, msg: SkillResourceRequest) -> None:
    rows = _lookup(msg.skill)
    await ctx.send(
        sender,
        SkillResourceResponse(
            resources=[ResourceItem(**r) for r in rows],
            request_id=msg.request_id,
            skill=msg.skill,
        ),
    )


if __name__ == "__main__":
    agent.run()
