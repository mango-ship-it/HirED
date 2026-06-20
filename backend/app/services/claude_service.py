"""Claude (Anthropic) integration — structured extraction + lesson generation.

Uses the async client (AsyncAnthropic) so FastAPI handlers stay non-blocking.
Structured JSON output is forced via `output_config.format` with a json_schema
(the current, reliable way to get a guaranteed-shape JSON object). Claude does
the EXTRACTION and the teaching copy; it never produces the numeric score.

Verified against the Anthropic Python SDK (anthropic==0.111.0):
  - client = AsyncAnthropic()  (reads ANTHROPIC_API_KEY from env)
  - await client.messages.create(model=, max_tokens=, system=, messages=,
        output_config={"format": {"type": "json_schema", "schema": {...}}})
  - the first text block contains valid JSON matching the schema.
"""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.extraction import EXTRACTION_JSON_SCHEMA, ExtractedProfile
from app.models.schemas import Lesson

logger = logging.getLogger("hired.claude")

# Lessons schema for forced JSON output (1-3 lessons).
_LESSONS_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "lessons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "title": {"type": "string"},
                    "principle": {"type": "string"},
                    "example": {"type": "string"},
                    "next_step": {"type": "string"},
                },
                "required": ["category", "title", "principle", "example", "next_step"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lessons"],
    "additionalProperties": False,
}

_EXTRACTION_SYSTEM = (
    "You are an expert technical recruiter and resume analyst for HirED, a career "
    "tutor for first-generation and low-income job seekers. Extract STRUCTURED FACTS "
    "from a candidate's resume/pitch text against a target role. Be precise and "
    "literal: count only quantified achievements that contain real numbers, metrics, "
    "or measurable impact. Parse the target text into the concrete skills the role "
    "requires, then determine which the candidate demonstrably has. Do NOT score, "
    "rank, or editorialize — only extract facts into the required JSON shape."
)

_LESSONS_SYSTEM = (
    "You are a supportive career tutor for HirED, teaching the 'hidden curriculum' of "
    "job hunting to first-generation and low-income job seekers. Given a candidate's "
    "lowest-scoring categories, write 1-3 micro-lessons that each move the needle. "
    "Each lesson has: a short title, a one-sentence PRINCIPLE (the rule), a concrete "
    "before/after EXAMPLE, and ONE specific NEXT STEP the user can do today. Be warm, "
    "concrete, and jargon-free. Frame everything as a teachable skill, never as a flaw."
)


class ClaudeService:
    """Thin wrapper over the async Anthropic client for HirED's two LLM jobs."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to backend/.env."
            )
        # AsyncAnthropic reads ANTHROPIC_API_KEY from the env; pass explicitly so a
        # value loaded into Settings from .env is honored even if not exported.
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model

    async def extract_profile(self, resume: str, target: str) -> ExtractedProfile:
        """Pull a structured ExtractedProfile from resume + target text.

        Raises on API failure so the route can return a clean 502 rather than a
        silently-wrong score.
        """
        user_content = (
            f"TARGET ROLE (company + role, or pasted job posting):\n{target}\n\n"
            f"CANDIDATE RESUME / PITCH / TRANSCRIPT:\n{resume}\n\n"
            "Extract the structured profile."
        )
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            output_config={
                "format": {"type": "json_schema", "schema": EXTRACTION_JSON_SCHEMA}
            },
        )
        data = _first_json(response)
        return ExtractedProfile.model_validate(data)

    async def generate_lessons(
        self,
        *,
        resume: str,
        target: str,
        categories: dict[str, int],
        profile: ExtractedProfile,
    ) -> list[Lesson]:
        """Generate 1-3 lessons for the weakest categories.

        Deterministically picks the lowest-scoring categories so the lessons always
        target the gaps that matter, then lets Claude write the teaching copy.
        """
        weakest = sorted(categories.items(), key=lambda kv: kv[1])[:3]
        focus = ", ".join(f"{name} ({value}/100)" for name, value in weakest)

        user_content = (
            f"TARGET: {profile.target_summary or target}\n"
            f"WEAKEST CATEGORIES (lowest score first): {focus}\n"
            f"MISSING SKILLS: {', '.join(profile.missing_skills) or 'none'}\n"
            f"QUANTIFIED ACHIEVEMENTS: {profile.quantified_achievement_count} "
            f"of {profile.total_achievement_count} bullets\n\n"
            f"RESUME EXCERPT:\n{resume[:1500]}\n\n"
            "Write 1-3 micro-lessons for the weakest categories above. Set each "
            "lesson's `category` to the matching weak-category name so the app can "
            "fetch resources for it."
        )
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=_LESSONS_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            output_config={
                "format": {"type": "json_schema", "schema": _LESSONS_JSON_SCHEMA}
            },
        )
        data = _first_json(response)
        return [Lesson.model_validate(item) for item in data.get("lessons", [])]


def _first_json(response) -> dict:
    """Extract and parse the first text block of a Messages response as JSON.

    With output_config.format the first text block is guaranteed to be valid JSON
    matching the schema. We still parse defensively and raise a clear error if the
    model refused (stop_reason == 'refusal') or returned no text.
    """
    if getattr(response, "stop_reason", None) == "refusal":
        raise RuntimeError("Claude refused the extraction/lesson request.")
    text = next(
        (block.text for block in response.content if block.type == "text"), None
    )
    if not text:
        raise RuntimeError("Claude returned no text content.")
    return json.loads(text)


# Lazily-built singleton so import never requires a key, but first use does.
_service: ClaudeService | None = None


def get_claude_service() -> ClaudeService:
    global _service
    if _service is None:
        _service = ClaudeService()
    return _service
