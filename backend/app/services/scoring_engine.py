"""Pluggable scoring — the contract-facing score + per-category step.

Pipeline: parse (document_parser) -> extract signals (extractor) -> SCORE (here).
This module makes the SCORE step swappable so a teammate's scorer can drop in
WITHOUT touching the /score route or the API contract.

Default = DeterministicScorer (MASTER.md §7 weighted formula). Claude never
produces the number — it only extracts the signals a scorer consumes.

== How a teammate plugs in their own scorer ==
1. Create `app/services/custom_scorer.py`:

       from app.services.scoring_engine import CategoryScore, ScoreOutcome

       class CustomScorer:
           name = "custom"
           async def score(self, *, profile, resume, target) -> ScoreOutcome:
               # ... your model / formula ...
               # MUST return the five snake_case contract categories so the
               # frontend's bars + benchmark chips keep working:
               return ScoreOutcome(score=72, categories={
                   "skills_match":            CategoryScore(score=65, weight=0.35),
                   "quantified_achievements": CategoryScore(score=40, weight=0.25),
                   "experience":              CategoryScore(score=80, weight=0.20),
                   "education":               CategoryScore(score=90, weight=0.10),
                   "clarity":                 CategoryScore(score=70, weight=0.10),
               })

2. Set `SCORER=custom` in `backend/.env`. That's it — no other changes.
   (Unknown/broken scorer -> we log and fall back to deterministic, so the page
   never breaks.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Protocol

from app.config import get_settings
from app.models.extraction import ExtractedProfile
from app.scoring import compute_score
from app.services.profile_signals import profile_to_signals

logger = logging.getLogger("hired.scoring")

# The five contract categories the frontend expects (snake_case).
CONTRACT_CATEGORIES = (
    "skills_match",
    "quantified_achievements",
    "experience",
    "education",
    "clarity",
)


@dataclass(frozen=True)
class CategoryScore:
    score: int  # 0-100
    weight: float


@dataclass(frozen=True)
class ScoreOutcome:
    """A scorer's result: overall 0-100 + per-category breakdown (snake_case keys)."""

    score: int
    categories: dict[str, CategoryScore]


class Scorer(Protocol):
    """Implement this to provide an alternative scoring engine."""

    name: str

    async def score(
        self, *, profile: ExtractedProfile, resume: str, target: str
    ) -> ScoreOutcome: ...


class DeterministicScorer:
    """Default scorer: the fixed weighted formula (MASTER.md §7). Pure + deterministic."""

    name = "deterministic"

    async def score(
        self, *, profile: ExtractedProfile, resume: str, target: str
    ) -> ScoreOutcome:
        result = compute_score(profile_to_signals(profile))
        return ScoreOutcome(
            score=result.score,
            categories={
                category.key: CategoryScore(score=category.score, weight=category.weight)
                for category in result.categories.values()
            },
        )


def _load_custom() -> Scorer:
    # Lazy import so the default path never depends on the (optional) teammate file.
    from app.services.custom_scorer import CustomScorer

    return CustomScorer()


# name -> factory. Add new scorers here.
_REGISTRY: dict[str, Callable[[], Scorer]] = {
    "deterministic": DeterministicScorer,
    "custom": _load_custom,
}


def get_scorer() -> Scorer:
    """Return the configured scorer (env SCORER), falling back to deterministic.

    Never raises: an unknown name or a broken custom scorer degrades to the
    deterministic scorer so the first page always works.
    """
    name = (get_settings().scorer or "deterministic").strip().lower()
    factory = _REGISTRY.get(name)
    if factory is None:
        logger.warning("Unknown SCORER=%r; using deterministic.", name)
        return DeterministicScorer()
    try:
        return factory()
    except Exception:
        logger.exception("Scorer %r failed to load; using deterministic.", name)
        return DeterministicScorer()
