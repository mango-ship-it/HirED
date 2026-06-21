"""Build a compact, grounded digest of REAL job postings for the lessons prompt.

Verified design (workflow wf_7fefb5ee — accuracy/hallucination/budget reviewed): inject
only what is genuinely NEW versus the existing lessons prompt — deduped job TITLES, 1-2
relevance-filtered requirement EXCERPTS, and the sample size N. The missing-skills list is
already in the prompt and already JD-overridden, so it is NOT re-injected. Excerpts are
filtered to a focus skill + a requirement cue so boilerplate/perks/EEO lines don't leak in.

Pure + deterministic + hard token-capped. Returns "" when there's nothing clean to add
(callers then fall through to the un-grounded prompt). No API cost.
"""

from __future__ import annotations

import re

_REQUIREMENT_CUES = (
    "experience", "required", "must", "proficient", "proficiency", "knowledge of",
    "ability to", "responsible for", "familiar with", "strong", "skills", "years",
    "degree", "expertise", "background in",
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.lower()[:60]
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _relevant_excerpts(jobs: list[dict], focus: list[str] | None, limit: int) -> list[str]:
    """Single-sentence requirement lines mentioning a focus skill (or any cue if no focus)."""
    focus_l = [f.lower() for f in (focus or []) if f]
    out: list[str] = []
    seen: set[str] = set()
    for job in jobs:
        for sentence in _sentences(job.get("description", "")):
            if not (15 <= len(sentence) <= 220):
                continue
            low = sentence.lower()
            if focus_l and not any(f in low for f in focus_l):
                continue
            if not any(cue in low for cue in _REQUIREMENT_CUES):
                continue
            key = low[:60]
            if key in seen:
                continue
            seen.add(key)
            out.append(sentence[:200])
            if len(out) >= limit:
                return out
    return out


def build_lesson_context(
    jobs: list[dict] | None,
    focus_skills: list[str] | None = None,
    *,
    max_titles: int = 4,
    max_excerpts: int = 2,
    max_chars: int = 2200,
) -> str:
    """Compact digest of real postings for the lessons prompt; "" if nothing usable."""
    if not jobs:
        return ""
    titles = _dedup(
        [(j.get("title") or "").strip()[:80] for j in jobs if (j.get("title") or "").strip()]
    )[:max_titles]
    excerpts = _relevant_excerpts(jobs, focus_skills, max_excerpts)
    if not titles and not excerpts:
        return ""
    lines = [
        f"REAL JOB POSTINGS FOR THE TARGET ROLE (employer language describing the "
        f"role/market — NOT facts about this candidate; across {len(jobs)} postings):"
    ]
    if titles:
        lines.append("Posting titles: " + "; ".join(titles))
    if excerpts:
        lines.append("Sample requirements employers wrote:")
        lines.extend(f'- "{e}"' for e in excerpts)
    return "\n".join(lines)[:max_chars]
