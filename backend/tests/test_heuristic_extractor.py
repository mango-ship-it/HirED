"""Tests for the dependency-free heuristic extractor + templated lessons."""
from app.models.extraction import ExtractedProfile
from app.services.heuristic_extractor import extract_profile_heuristic, heuristic_lessons


def test_matches_target_skills_against_resume():
    profile = extract_profile_heuristic("I write Python and some SQL.", "Need Python, SQL, Tableau")
    assert isinstance(profile, ExtractedProfile)
    assert "Python" in profile.matched_skills
    assert "Tableau" in profile.missing_skills


def test_counts_quantified_and_years():
    profile = extract_profile_heuristic(
        "Grew sales 30% over 4 years. Cut costs 15%.", "Analyst"
    )
    assert profile.quantified_achievement_count >= 2
    assert profile.years_experience == 4.0


def test_detects_education():
    assert extract_profile_heuristic("Bachelor's degree in CS", "x").education_level == "bachelor"


def test_vague_target_grades_against_resume_skills():
    # No vocab skills in the target -> fall back to the candidate's own skills so
    # skills_match isn't an unfair zero.
    profile = extract_profile_heuristic("Python and Docker engineer", "a great job")
    assert profile.required_skills  # non-empty
    assert "Python" in profile.matched_skills


def test_lessons_target_the_weakest_categories():
    lessons = heuristic_lessons(
        {"skills_match": 10, "quantified_achievements": 20, "experience": 90, "education": 80, "clarity": 70}
    )
    assert 1 <= len(lessons) <= 3
    categories = {lesson.category for lesson in lessons}
    assert "skills_match" in categories  # the lowest-scoring category
