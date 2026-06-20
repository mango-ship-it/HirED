"""Tests for the deterministic scoring engine (MASTER.md §7).

Written first (TDD): these define the contract the implementation must satisfy.
The formula is fixed and must be deterministic — same signals in, same score out.
"""
import math

import pytest

from app.scoring import (
    WEIGHTS,
    Category,
    ScoreResult,
    clamp01,
    compute_score,
    education_signal,
    experience_signal,
    quantified_signal,
    skills_match_signal,
)


def test_weights_sum_to_one():
    assert math.isclose(sum(WEIGHTS.values()), 1.0, abs_tol=1e-9)


def test_weights_have_expected_keys():
    assert set(WEIGHTS) == {
        "skills_match",
        "quantified_achievements",
        "experience",
        "education",
        "clarity",
    }


@pytest.mark.parametrize(
    "value,expected",
    [(-1.0, 0.0), (0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (2.0, 1.0)],
)
def test_clamp01_bounds(value, expected):
    assert clamp01(value) == expected


def test_clamp01_rejects_nan():
    with pytest.raises(ValueError):
        clamp01(float("nan"))


def test_skills_match_ratio():
    assert skills_match_signal(3, 6) == 0.5


def test_skills_match_clamped_above_one():
    assert skills_match_signal(10, 5) == 1.0


def test_skills_match_no_requirements_is_zero():
    # Nothing required -> we cannot assess fit -> 0.0 (not a free pass).
    assert skills_match_signal(0, 0) == 0.0


def test_skills_match_rejects_negatives():
    with pytest.raises(ValueError):
        skills_match_signal(-1, 5)


def test_quantified_signal_proxy():
    assert quantified_signal(0) == 0.0
    assert quantified_signal(100) == 1.0  # clamped


def test_experience_signal_proxy():
    assert experience_signal(0) == 0.0
    assert experience_signal(100) == 1.0  # clamped


def test_education_signal_ladder_is_monotonic():
    levels = ["none", "high_school", "some_college", "bachelor", "master", "doctorate"]
    scores = [education_signal(lvl) for lvl in levels]
    assert scores == sorted(scores)
    assert education_signal("doctorate") == 1.0


def test_education_signal_unknown_level_raises():
    with pytest.raises(ValueError):
        education_signal("wizard")


def _all(value: float) -> dict[str, float]:
    return {k: value for k in WEIGHTS}


def test_perfect_score_is_100():
    result = compute_score(_all(1.0))
    assert result.score == 100


def test_zero_score_is_0():
    result = compute_score(_all(0.0))
    assert result.score == 0


def test_single_category_contribution():
    # Only skills_match maxed -> 0.35 * 100 = 35 overall.
    signals = _all(0.0)
    signals["skills_match"] = 1.0
    result = compute_score(signals)
    assert result.score == 35
    assert result.categories["skills_match"].score == 100
    assert result.categories["quantified_achievements"].score == 0


def test_compute_is_deterministic():
    signals = {
        "skills_match": 0.8,
        "quantified_achievements": 0.4,
        "experience": 0.6,
        "education": 0.8,
        "clarity": 0.5,
    }
    assert compute_score(signals).score == compute_score(dict(signals)).score


def test_missing_signal_raises():
    signals = _all(0.5)
    del signals["clarity"]
    with pytest.raises(ValueError):
        compute_score(signals)


def test_unexpected_signal_raises():
    signals = _all(0.5)
    signals["vibes"] = 0.9
    with pytest.raises(ValueError):
        compute_score(signals)


def test_compute_does_not_mutate_input():
    signals = _all(0.5)
    snapshot = dict(signals)
    compute_score(signals)
    assert signals == snapshot


def test_result_is_immutable():
    result = compute_score(_all(0.5))
    with pytest.raises(Exception):
        result.score = 99  # frozen dataclass


def test_payload_shape_uses_human_labels():
    payload = compute_score(_all(1.0)).to_payload()
    assert payload["score"] == 100
    assert "Skills Match" in payload["categories"]
    assert "Quantified Impact" in payload["categories"]
    assert payload["categories"]["Skills Match"]["score"] == 100
