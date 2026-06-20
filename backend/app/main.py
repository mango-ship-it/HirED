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
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routes import agents as agents_routes
from app.routes import jobs as jobs_routes
from app.routes import profile as profile_routes
from app.routes import report as report_routes
from app.routes import score as score_routes
from app.routes import voice as voice_routes
from app.services.store import get_store

logging.basicConfig(level=logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the per-user store (Redis if reachable, else in-memory) for the app's life."""
    await get_store().connect()
    yield
    await get_store().aclose()


app = FastAPI(
    title="HirED API",
    version="0.1.0",
    description="AI career tutor backend — score, benchmark, resources, voice.",
    lifespan=lifespan,
)

# CORS so the Vite/React frontend can call us directly.
# Out of the box we allow ANY locally-served frontend (any localhost / 127.0.0.1
# port) — so every teammate running the frontend on their own machine works with no
# config — plus any explicit origins in CORS_ORIGINS (e.g. a deployed frontend URL).
# Set CORS_ORIGINS=* to open it to everything (this disables credentials); only do
# that briefly — an open, key-holding backend can have its Claude credits used by anyone.
_cors_origins = settings.cors_origin_list
if "*" in _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
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
app.include_router(profile_routes.router, tags=["profile"])
app.include_router(jobs_routes.router, tags=["jobs"])


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    """Friendly landing for the base URL — the API lives under named paths."""
    return {
        "service": "HirED API",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["meta"])
async def health() -> dict[str, object]:
    """Liveness + config visibility (no secrets leaked — booleans only)."""
    return {
        "status": "ok",
        "claude_configured": bool(settings.anthropic_api_key),
        "deepgram_configured": bool(settings.deepgram_api_key),
        "resource_agent_configured": bool(settings.resource_agent_address),
        "benchmark_agent_configured": bool(settings.benchmark_agent_address),
        "store": get_store().backend,
    }
