"""Integration tests for the 2AFC + ELO pipeline in benchmark_agent."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_2afc_pipeline_returns_int_percentile():
    """_run_2afc_pipeline should return (percentile: int, sample_size: int)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from agents.benchmark_agent import _run_2afc_pipeline

    fake_competitors = ["Candidate A resume text"] * 8

    with patch("agents.benchmark_agent.synthesize_cohort", new=AsyncMock(return_value=fake_competitors)), \
         patch("agents.benchmark_agent.judge_pair", new=AsyncMock(return_value="A")), \
         patch("agents.benchmark_agent._load_jd", return_value="Software Engineer JD"):
        percentile, sample_size = await _run_2afc_pipeline("User resume proxy", "SWE Intern")

    assert isinstance(percentile, int)
    assert 0 <= percentile <= 100
    assert sample_size == 8


@pytest.mark.asyncio
async def test_run_2afc_pipeline_user_wins_all_gives_high_percentile():
    """If user beats all 8 competitors, percentile should be 100."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from agents.benchmark_agent import _run_2afc_pipeline

    fake_competitors = ["Competitor resume"] * 8

    with patch("agents.benchmark_agent.synthesize_cohort", new=AsyncMock(return_value=fake_competitors)), \
         patch("agents.benchmark_agent.judge_pair", new=AsyncMock(return_value="A")), \
         patch("agents.benchmark_agent._load_jd", return_value="JD text"):
        percentile, _ = await _run_2afc_pipeline("User proxy", "ML Intern")

    assert percentile == 100


@pytest.mark.asyncio
async def test_run_2afc_pipeline_user_loses_all_gives_low_percentile():
    """If user loses all 8, percentile should be 0."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from agents.benchmark_agent import _run_2afc_pipeline

    fake_competitors = ["Competitor resume"] * 8

    with patch("agents.benchmark_agent.synthesize_cohort", new=AsyncMock(return_value=fake_competitors)), \
         patch("agents.benchmark_agent.judge_pair", new=AsyncMock(return_value="B")), \
         patch("agents.benchmark_agent._load_jd", return_value="JD text"):
        percentile, _ = await _run_2afc_pipeline("User proxy", "ML Intern")

    assert percentile == 0


@pytest.mark.asyncio
async def test_run_2afc_pipeline_falls_back_on_synthesis_timeout():
    """If synthesize_cohort times out, _SEED_COMPETITORS is used as fallback."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from agents.benchmark_agent import _run_2afc_pipeline, _SEED_COMPETITORS

    async def _slow_synthesis(*args, **kwargs):
        await asyncio.sleep(9999)
        return []

    with patch("agents.benchmark_agent.synthesize_cohort", side_effect=_slow_synthesis), \
         patch("agents.benchmark_agent.judge_pair", new=AsyncMock(return_value="A")), \
         patch("agents.benchmark_agent._load_jd", return_value="JD text"), \
         patch("agents.benchmark_agent._SYNTHESIS_TIMEOUT", 0.01):
        percentile, sample_size = await _run_2afc_pipeline("User proxy", "SWE Intern")

    assert isinstance(percentile, int)
    assert sample_size == len(_SEED_COMPETITORS)
