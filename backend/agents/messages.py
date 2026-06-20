"""Shared uAgent message models.

Both the agents (agents/*.py) and the FastAPI bridge (app/services/fetch_bridge.py)
import these so the request/response shapes can't drift. uAgents' `Model` is a
pydantic model under the hood.
"""

from __future__ import annotations

from uagents import Model


class ResourceRequest(Model):
    gap_category: str
    context: str = ""


class ResourceResponse(Model):
    resources: list[str]


class BenchmarkRequest(Model):
    score: int
    target: str


class BenchmarkResponse(Model):
    percentile: int
