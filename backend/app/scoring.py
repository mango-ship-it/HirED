"""Deterministic compatibility scoring (MASTER.md §7).

The score is a fixed weighted formula — Claude extracts the raw signals, but it
never invents the number. Same signals in, same score out. That determinism is
what makes the re-score demo land: fix a gap, watch the number move.

This module is pure (no I/O, no external deps) and immutable (every function
returns a new value; nothing is mutated in place).
"""
from __future__ import annotations

from dataclasses import dataclass

# Fixed weights — must sum to 1.0. Sourced from research, not vibes (MASTER.md §7):
# quantified work + skills-match are weighted highest; years/education are weak
# predictors of performance (Schmidt & Hunter), so they carry less.
WEIGHTS: dict[str, float] = {
    "skills_match": 0.35,
    "quantified_achievements": 0.25,
    "experience": 0.20,
    "education": 0.10,
    "clarity": 0.10,
}

# Human-facing labels — every score is framed as a learnable skill, never a bare
# number (FRONTEND.md educational-design principle).
CATEGORY_LABELS: dict[str, str] = {
    "skills_match": "Skills Match",
    "quantified_achievements": "Quantified Impact",
    "experience": "Relevant Experience",
    "education": "Education",
    "clarity": "Clarity & Communication",
}

# A category counts as a "gap" worth coaching only below this score. A stronger resume has
# fewer categories below it, so it shows fewer gaps (e.g. 2 instead of 3).
GAP_THRESHOLD = 70


def select_gaps(
    category_scores: dict[str, int], *, threshold: int = GAP_THRESHOLD, max_gaps: int = 3
) -> list[tuple[str, int]]:
    """The genuine gaps to coach: categories below `threshold`, weakest first, capped at
    `max_gaps`. A better resume -> fewer weak categories -> fewer gaps. Always returns at
    least the single weakest, so there's always one concrete next step."""
    ranked = sorted(category_scores.items(), key=lambda kv: kv[1])
    gaps = [(name, score) for name, score in ranked if score < threshold][:max_gaps]
    return gaps or ranked[:1]

# Simple, documented proxies for normalizing raw signals to 0..1.
TARGET_QUANTIFIED_BULLETS = 5  # >= 5 quantified bullets earns full marks
TARGET_RELEVANT_YEARS = 5.0  # >= 5 relevant years earns full marks
EDUCATION_LADDER: dict[str, float] = {
    "none": 0.0,
    "high_school": 0.3,
    "some_college": 0.5,
    "associate": 0.6,
    "bachelor": 0.8,
    "master": 0.95,
    "doctorate": 1.0,
}


def clamp01(x: float) -> float:
    """Clamp a value into the inclusive range [0.0, 1.0]."""
    value = float(x)
    if value != value:  # NaN never equals itself
        raise ValueError("score signal must be a real number, got NaN")
    return max(0.0, min(1.0, value))


def skills_match_signal(matched: int, required: int) -> float:
    """matched / required, clamped to [0, 1].

    If the target has no required skills we cannot assess fit, so this returns
    0.0 (not a free pass) — the target parser is expected to supply requirements.
    """
    if matched < 0 or required < 0:
        raise ValueError("matched/required counts must be non-negative")
    if required == 0:
        return 0.0
    return clamp01(matched / required)


def quantified_signal(quantified_bullets: int, target: int = TARGET_QUANTIFIED_BULLETS) -> float:
    """Proxy: fraction of the target number of quantified achievement bullets."""
    if quantified_bullets < 0:
        raise ValueError("quantified_bullets must be non-negative")
    if target <= 0:
        raise ValueError("target must be positive")
    return clamp01(quantified_bullets / target)


def experience_signal(relevant_years: float, target: float = TARGET_RELEVANT_YEARS) -> float:
    """Proxy: fraction of the target years of relevant experience."""
    if relevant_years < 0:
        raise ValueError("relevant_years must be non-negative")
    if target <= 0:
        raise ValueError("target must be positive")
    return clamp01(relevant_years / target)


def education_signal(level: str) -> float:
    """Map an education level onto the 0..1 ladder."""
    key = (level or "").strip().lower()
    if key not in EDUCATION_LADDER:
        raise ValueError(
            f"unknown education level: {level!r}; expected one of {sorted(EDUCATION_LADDER)}"
        )
    return EDUCATION_LADDER[key]


@dataclass(frozen=True)
class Category:
    """One scored category, on a 0..100 scale, with its weight and contribution."""

    key: str
    label: str
    score: int  # 0..100, the normalized signal
    weight: float
    contribution: float  # weighted points this category added to the overall score


@dataclass(frozen=True)
class ScoreResult:
    """Overall 0..100 score plus the per-category breakdown."""

    score: int
    categories: dict[str, Category]

    def to_payload(self) -> dict:
        """Shape for the `POST /score` response (FRONTEND.md contract)."""
        return {
            "score": self.score,
            "categories": {
                category.label: {
                    "score": category.score,
                    "weight": category.weight,
                    "contribution": round(category.contribution, 1),
                }
                for category in self.categories.values()
            },
        }


def compute_score(signals: dict[str, float]) -> ScoreResult:
    """Compute the overall 0..100 score and per-category breakdown from 0..1 signals.

    ``signals`` must contain exactly the :data:`WEIGHTS` keys, each already
    normalized to [0, 1] (use the ``*_signal`` helpers above). The input is never
    mutated; a new immutable :class:`ScoreResult` is returned.
    """
    missing = set(WEIGHTS) - set(signals)
    if missing:
        raise ValueError(f"missing score signals: {sorted(missing)}")
    unexpected = set(signals) - set(WEIGHTS)
    if unexpected:
        raise ValueError(f"unexpected score signals: {sorted(unexpected)}")

    categories: dict[str, Category] = {}
    overall = 0.0
    for key, weight in WEIGHTS.items():
        normalized = clamp01(signals[key])
        contribution = normalized * weight * 100.0
        overall += contribution
        categories[key] = Category(
            key=key,
            label=CATEGORY_LABELS[key],
            score=round(normalized * 100),
            weight=weight,
            contribution=contribution,
        )
    return ScoreResult(score=round(overall), categories=categories)
