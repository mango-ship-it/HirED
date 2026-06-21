"""ELO rating aggregation for the 2AFC benchmark pipeline.

Each pairwise 2AFC result (user vs. one competitor) feeds into ELO updates.
After all comparisons, the user's ELO rating is converted to a percentile
against the same cohort — "ahead of X% of candidates for this role."

K=32 (standard for smaller cohorts / short match series).
All ratings start at 1000.
"""

from __future__ import annotations

_INITIAL_RATING = 1000.0
_K = 32


def elo_update(
    rating_a: float, rating_b: float, winner: str
) -> tuple[float, float]:
    """Return updated (rating_a, rating_b) after one match.

    winner must be 'A' or 'B'.
    """
    expected_a = 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))
    expected_b = 1.0 - expected_a
    score_a = 1.0 if winner == "A" else 0.0
    score_b = 1.0 - score_a
    new_a = rating_a + _K * (score_a - expected_a)
    new_b = rating_b + _K * (score_b - expected_b)
    return new_a, new_b


def run_tournament(user_resume: str, competitors: list[str], winners: list[str]) -> float:
    """Run user vs. each competitor through ELO; return the user's final rating.

    winners[i] is 'A' (user won) or 'B' (competitor won) for match i.
    Competitor ratings are independent across matches (fresh 1000 each time)
    since we don't have prior history for them.
    """
    user_rating = _INITIAL_RATING
    for winner in winners:
        competitor_rating = _INITIAL_RATING
        user_rating, _ = elo_update(user_rating, competitor_rating, winner)
    return user_rating


def rating_to_percentile(user_rating: float, cohort_ratings: list[float]) -> int:
    """Percent of cohort the user's ELO beats (0–100)."""
    if not cohort_ratings:
        return 50
    beaten = sum(1 for r in cohort_ratings if user_rating > r)
    return max(0, min(100, round(100 * beaten / len(cohort_ratings))))


def win_rate_to_percentile(wins: int, total: int) -> int:
    """Simple win-rate percentile when cohort baseline is unknown.

    Used as a fallback when full ELO data is unavailable.
    """
    if total == 0:
        return 50
    return max(0, min(100, round(100 * wins / total)))
