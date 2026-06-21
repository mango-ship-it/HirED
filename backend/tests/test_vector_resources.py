"""Tests for the semantic-resource layer (degradation path — no Redis/index in tests)."""
import asyncio

from app.data.resources import RESOURCE_CORPUS, corpus_for
from app.services import vector_resources


def test_corpus_is_populated_and_tagged():
    assert RESOURCE_CORPUS
    categories = {r["gap_category"] for r in RESOURCE_CORPUS}
    assert {"skills_match", "quantified_achievements", "clarity"} <= categories
    assert all(r["name"] and r["url"] and r["description"] for r in RESOURCE_CORPUS)


def test_corpus_for_filters_by_category():
    rows = corpus_for("clarity")
    assert rows and all(r["gap_category"] == "clarity" for r in rows)


def test_search_returns_none_when_index_not_built():
    # The index is built only in the app lifespan; in tests it's never built, so the
    # semantic layer degrades to None and /resources falls back to the static list.
    assert asyncio.run(vector_resources.search("quantified impact")) is None
    assert vector_resources.status() in ("not_built", "failed")
