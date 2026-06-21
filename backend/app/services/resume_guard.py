"""Shared guard: does a string contain enough real content to be a resume?

Every path that feeds /score (file upload, pasted text, the transcribe->score
flow) enforces the SAME floor here, so a near-empty input — a stray page number,
a lone "." or "N/A" from a scanned PDF, a one-word voice transcript — is never
scored as a real resume and never yields a misleading low-but-non-zero number.
"""

from __future__ import annotations

import re

# A resume needs at least this many alphabetic word tokens (>= 2 letters) to be
# scoreable. Low enough to accept a terse real resume, high enough to reject a
# stray glyph, page number, or bare job-title fragment.
MIN_RESUME_WORDS = 3

_WORD = re.compile(r"[A-Za-z]{2,}")


def resume_word_count(text: str) -> int:
    """Count alphabetic word tokens (>= 2 letters) — the real-content signal."""
    return len(_WORD.findall(text or ""))


def has_usable_resume(text: str) -> bool:
    """True when `text` has enough real content to be scored as a resume."""
    return resume_word_count(text) >= MIN_RESUME_WORDS
