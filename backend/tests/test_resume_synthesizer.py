"""Tests for app/services/resume_synthesizer.py."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.resume_synthesizer import (
    Tier,
    _fallback_for_tier,
    synthesize_cohort,
    synthesize_resume,
)


# ── _fallback_for_tier ────────────────────────────────────────────────────────

def test_fallback_strong_returns_nonempty():
    text = _fallback_for_tier("strong")
    assert isinstance(text, str) and len(text) > 50


def test_fallback_average_returns_nonempty():
    text = _fallback_for_tier("average")
    assert isinstance(text, str) and len(text) > 50


def test_fallback_weak_returns_nonempty():
    text = _fallback_for_tier("weak")
    assert isinstance(text, str) and len(text) > 50


# ── synthesize_resume ─────────────────────────────────────────────────────────

_FAKE_JD = "Software Engineer Intern — Python, ML experience preferred."
_FAKE_TARGET = "ML Engineer Intern"


def _make_openai_response(content: str):
    """Build a minimal mock that looks like an AsyncOpenAI chat completion."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_synthesize_resume_uses_tokenrouter_when_key_present():
    fake_resume = "Jane Doe | ML Intern\nEducation: BS Computer Science, MIT, GPA 3.9 (2024)\nExperience:\n  - ML Intern @ Google (Jun–Aug 2023, 3 mo)\n    * Trained models on dataset; achieved 95% accuracy\nSkills: Python, PyTorch, TensorFlow"
    mock_response = _make_openai_response(fake_resume)

    with patch("app.services.resume_synthesizer.get_settings") as mock_cfg, \
         patch("openai.AsyncOpenAI") as mock_cls:
        settings = MagicMock()
        settings.token_router_api_key = "tr-fake-key"
        settings.token_router_base_url = "https://api.tokenrouter.com/v1"
        settings.token_router_model = "auto"
        mock_cfg.return_value = settings

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        result = await synthesize_resume(_FAKE_JD, "strong", _FAKE_TARGET)

    assert result == fake_resume


@pytest.mark.asyncio
async def test_synthesize_resume_falls_back_when_no_key():
    with patch("app.services.resume_synthesizer.get_settings") as mock_cfg:
        settings = MagicMock()
        settings.token_router_api_key = ""
        mock_cfg.return_value = settings

        result = await synthesize_resume(_FAKE_JD, "average", _FAKE_TARGET)

    assert isinstance(result, str) and len(result) > 50


@pytest.mark.asyncio
async def test_synthesize_resume_falls_back_on_exception():
    with patch("app.services.resume_synthesizer.get_settings") as mock_cfg, \
         patch("openai.AsyncOpenAI") as mock_cls:
        settings = MagicMock()
        settings.token_router_api_key = "tr-fake-key"
        settings.token_router_base_url = "https://api.tokenrouter.com/v1"
        settings.token_router_model = "auto"
        mock_cfg.return_value = settings

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("network error")
        )
        mock_cls.return_value = mock_client

        result = await synthesize_resume(_FAKE_JD, "weak", _FAKE_TARGET)

    assert isinstance(result, str) and len(result) > 50


@pytest.mark.asyncio
async def test_synthesize_resume_falls_back_on_too_short_response():
    """If the model returns suspiciously short text, fall back to static."""
    mock_response = _make_openai_response("ok")

    with patch("app.services.resume_synthesizer.get_settings") as mock_cfg, \
         patch("openai.AsyncOpenAI") as mock_cls:
        settings = MagicMock()
        settings.token_router_api_key = "tr-fake-key"
        settings.token_router_base_url = "https://api.tokenrouter.com/v1"
        settings.token_router_model = "auto"
        mock_cfg.return_value = settings

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        result = await synthesize_resume(_FAKE_JD, "strong", _FAKE_TARGET)

    # fallback kicks in because response is < 100 chars
    assert len(result) > 50


# ── synthesize_cohort ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesize_cohort_default_returns_8():
    fake = "Jane Doe | Role\nEducation: BS CS, MIT"

    async def _fake_synthesize(jd, tier, target):
        return fake

    with patch("app.services.resume_synthesizer.synthesize_resume", side_effect=_fake_synthesize):
        result = await synthesize_cohort(_FAKE_JD, _FAKE_TARGET)

    assert len(result) == 8


@pytest.mark.asyncio
async def test_synthesize_cohort_custom_counts():
    fake = "Jane Doe | Role\nEducation: BS CS, MIT"

    async def _fake_synthesize(jd, tier, target):
        return fake

    with patch("app.services.resume_synthesizer.synthesize_resume", side_effect=_fake_synthesize):
        result = await synthesize_cohort(_FAKE_JD, _FAKE_TARGET, n_strong=1, n_average=2, n_weak=1)

    assert len(result) == 4


@pytest.mark.asyncio
async def test_synthesize_cohort_returns_list_of_strings():
    fake = "Jane Doe | Role\nEducation: BS CS, MIT"

    async def _fake_synthesize(jd, tier, target):
        return fake

    with patch("app.services.resume_synthesizer.synthesize_resume", side_effect=_fake_synthesize):
        result = await synthesize_cohort(_FAKE_JD, _FAKE_TARGET)

    assert all(isinstance(r, str) for r in result)
