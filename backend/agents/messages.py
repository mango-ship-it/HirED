"""Shared uAgent message models.

Both the agents (agents/*.py) and the FastAPI bridge (app/services/fetch_bridge.py)
import these so the request/response wire shapes can't drift. uAgents' `Model` is a
pydantic v2 model under the hood, so nested models (ResourceItem) work fine.
"""

from __future__ import annotations

from uagents import Model


class ResourceItem(Model):
    name: str
    url: str
    description: str


class ResourceRequest(Model):
    gap_category: str
    context: str = ""


class ResourceResponse(Model):
    resources: list[ResourceItem]


class BenchmarkRequest(Model):
    score: int
    target: str


class Match(Model):
    """One 2AFC head-to-head between the user and a synthesized competitor."""
    competitor_headline: str
    competitor_resume: str
    user_won: bool


class BenchmarkResponse(Model):
    percentile: int
    sample_size: int
    matches: list[Match] = []
