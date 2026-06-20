"""Ingest Sai-gathered data (jobs + mentors) from a local export file.

Sai (Simular) runs as a macOS app. The **pysimular** client drives it, but `run()`
blocks on a Cocoa run loop for minutes, so it can't live inside an API request. The
integration: `scripts/sai_fetch.py` runs pysimular on the Mac to gather live LinkedIn
jobs + mentor profiles and writes them to a JSON file; the backend reads that file
here (point `SAI_DATA_PATH` at it). A seed file ships so the demo never depends on a
live Sai run.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import get_settings
from app.models.report import Job, Mentor

logger = logging.getLogger("hired.sai")

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "sai_seed.json"


def _load() -> dict:
    configured = get_settings().sai_data_path
    path = Path(configured) if configured else _DEFAULT_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # missing/invalid file -> empty, never crash the report
        logger.warning("Sai data unavailable at %s (%s); returning empty.", path, exc)
        return {"jobs": [], "mentors": []}


def load_jobs(target: str, *, limit: int = 5) -> list[Job]:
    rows = _load().get("jobs", [])
    out: list[Job] = []
    for row in rows[:limit]:
        try:
            out.append(Job(**row))
        except Exception:
            logger.warning("Skipping malformed Sai job row: %r", row)
    return out


def load_mentors(target: str, *, limit: int = 3) -> list[Mentor]:
    rows = _load().get("mentors", [])
    out: list[Mentor] = []
    for row in rows[:limit]:
        try:
            out.append(Mentor(**row))
        except Exception:
            logger.warning("Skipping malformed Sai mentor row: %r", row)
    return out
