"""Company-specific LeetCode practice, pulled from a public GitHub dataset.

Source: github.com/snehasishroy/leetcode-companywise-interview-questions — 657 company
folders, each with CSVs (thirty-days / three-months / six-months / all) of the form
`ID,URL,Title,Difficulty,Acceptance %,Frequency %`, already sorted by frequency.

We fetch the per-company CSV from the raw CDN (no rate limit) on demand and cache the
parsed problems in Redis for 30 days, so a target like "Software Engineer at Google"
can surface the exact problems that company asks most. Everything degrades gracefully:
unknown company / network failure -> None (callers fall back to a generic LeetCode link).
Free + no API key.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import urllib.error
import urllib.request

import asyncio

from app.services.store import get_store

logger = logging.getLogger("hired.leetcode")

_RAW_BASE = "https://raw.githubusercontent.com/snehasishroy/leetcode-companywise-interview-questions/master"
_API_CONTENTS = "https://api.github.com/repos/snehasishroy/leetcode-companywise-interview-questions/contents/"
PERIODS = ("thirty-days", "three-months", "six-months", "more-than-six-months", "all")
_DEFAULT_PERIOD = "thirty-days"
_THIRTY_DAYS = 30 * 24 * 3600


def _slug(company: str) -> str:
    """Normalize a company name to the repo's folder slug ('Goldman Sachs'->'goldman-sachs')."""
    return re.sub(r"[^a-z0-9]+", "-", (company or "").strip().lower()).strip("-")


def parse_csv(text: str, *, limit: int | None = None) -> list[dict]:
    """Parse a company CSV into problems (already ordered by frequency)."""
    problems: list[dict] = []
    for row in csv.DictReader(io.StringIO(text)):
        title = (row.get("Title") or "").strip()
        url = (row.get("URL") or "").strip()
        if not title or not url:
            continue
        diff = (row.get("Difficulty") or "").strip()
        acc = (row.get("Acceptance %") or "").strip()
        problems.append({
            "id": (row.get("ID") or "").strip(),
            "title": title,
            "url": url,
            "difficulty": diff,
            "acceptance": acc,
            "frequency": (row.get("Frequency %") or "").strip(),
            "description": f"{diff} difficulty" + (f" · {acc} acceptance" if acc else ""),
        })
    return problems[:limit] if limit else problems


def _http_get(url: str, *, timeout: int = 8) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "HirED/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed host)
        return resp.read().decode("utf-8", errors="replace")


async def fetch_company_problems(
    company: str, *, period: str = _DEFAULT_PERIOD, limit: int = 15
) -> list[dict] | None:
    """Top LeetCode problems a company asks (Redis-cached). None if unknown/unavailable."""
    slug = _slug(company)
    if not slug:
        return None
    if period not in PERIODS:
        period = _DEFAULT_PERIOD
    cache_key = f"leetcode:{slug}:{period}"
    try:
        cached = await get_store().get_json(cache_key)
    except Exception:
        cached = None
    if cached is not None:
        return cached[:limit]
    try:
        text = await asyncio.to_thread(_http_get, f"{_RAW_BASE}/{slug}/{period}.csv")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None  # no such company / period
        logger.info("leetcode fetch failed for %s (%s)", slug, exc)
        return None
    except Exception as exc:
        logger.info("leetcode fetch failed for %s (%s)", slug, exc)
        return None
    problems = parse_csv(text)
    if not problems:
        return None
    try:
        await get_store().set_json(cache_key, problems, ttl=_THIRTY_DAYS)
    except Exception:
        pass  # cache is best-effort
    return problems[:limit]


async def known_companies() -> set[str]:
    """The set of company folder slugs (Redis-cached 30d). Empty set on failure."""
    try:
        cached = await get_store().get_json("leetcode:companies")
    except Exception:
        cached = None
    if cached:
        return set(cached)
    try:
        data = json.loads(await asyncio.to_thread(_http_get, _API_CONTENTS, timeout=10))
        names = [e["name"] for e in data if e.get("type") == "dir"]
    except Exception as exc:
        logger.info("leetcode company-list fetch failed (%s)", exc)
        return set()
    try:
        await get_store().set_json("leetcode:companies", names, ttl=_THIRTY_DAYS)
    except Exception:
        pass
    return set(names)


async def detect_company(text: str) -> str | None:
    """Find a known company named in free text (e.g. a target). None if none found."""
    if not text:
        return None
    low = text.lower()
    companies = await known_companies()
    hits = [c for c in companies if len(c) >= 4 and c.replace("-", " ") in low]
    return max(hits, key=len) if hits else None  # prefer the most specific match
