"""Tests for the pluggable scoring seam.

Covers the default deterministic scorer, the safe fallback for an unknown scorer,
and that a teammate's custom scorer drops in via the registry + SCORER setting.
"""
import asyncio

from app.models.extraction import ExtractedProfile
from app.services import scoring_engine
from app.services.scoring_engine import (
    CONTRACT_CATEGORIES,
    CategoryScore,
    DeterministicScorer,
    ScoreOutcome,
    get_scorer,
)


def _profile() -> ExtractedProfile:
    return ExtractedProfile(
        required_skills=["Python", "SQL"],
        matched_skills=["Python"],
        missing_skills=["SQL"],
        quantified_achievement_count=3,
        total_achievement_count=5,
        years_experience=2.0,
        education_level="bachelor",
        clarity_signal=0.6,
        target_summary="Data Analyst",
    )


def test_deterministic_scorer_returns_contract_categories():
    outcome = asyncio.run(DeterministicScorer().score(profile=_profile(), resume="r", target="t"))
    assert isinstance(outcome, ScoreOutcome)
    assert set(outcome.categories) == set(CONTRACT_CATEGORIES)
    assert 0 <= outcome.score <= 100


def test_get_scorer_defaults_to_deterministic():
    assert isinstance(get_scorer(), DeterministicScorer)


def test_unknown_scorer_falls_back_to_deterministic(monkeypatch):
    monkeypatch.setattr(scoring_engine, "get_settings", lambda: type("S", (), {"scorer": "nope"})())
    assert isinstance(get_scorer(), DeterministicScorer)


def test_custom_scorer_plugs_in(monkeypatch):
    class FakeScorer:
        name = "fake"

        async def score(self, *, profile, resume, target):
            return ScoreOutcome(
                score=88,
                categories={k: CategoryScore(score=88, weight=0.2) for k in CONTRACT_CATEGORIES},
            )

    monkeypatch.setattr(scoring_engine, "get_settings", lambda: type("S", (), {"scorer": "fake"})())
    monkeypatch.setitem(scoring_engine._REGISTRY, "fake", lambda: FakeScorer())

    scorer = get_scorer()
    assert scorer.name == "fake"
    outcome = asyncio.run(scorer.score(profile=_profile(), resume="r", target="t"))
    assert outcome.score == 88
