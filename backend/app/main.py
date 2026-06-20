"""HirED FastAPI app — entrypoint.

Run (after the two uAgents are up and their addresses are in .env):
    uvicorn app.main:app --reload

The 3-process setup (MASTER.md §8):
    python agents/resource_agent.py
    python agents/benchmark_agent.py
    uvicorn app.main:app
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routes import agents as agents_routes
from app.routes import report as report_routes
from app.routes import score as score_routes
from app.routes import voice as voice_routes

logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(
    title="HirED API",
    version="0.1.0",
    description="AI career tutor backend — score, benchmark, resources, voice.",
)

# CORS so the Vite/React frontend can call us directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated narration audio. /static/audio/<file>.mp3
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Routes (paths match the locked contract exactly — no prefix).
app.include_router(score_routes.router, tags=["score"])
app.include_router(agents_routes.router, tags=["agents"])
app.include_router(voice_routes.router, tags=["voice"])
app.include_router(report_routes.router, tags=["report"])


@app.get("/health", tags=["meta"])
async def health() -> dict[str, object]:
    """Liveness + config visibility (no secrets leaked — booleans only)."""
    return {
        "status": "ok",
        "claude_configured": bool(settings.anthropic_api_key),
        "deepgram_configured": bool(settings.deepgram_api_key),
        "resource_agent_configured": bool(settings.resource_agent_address),
        "benchmark_agent_configured": bool(settings.benchmark_agent_address),
    }
