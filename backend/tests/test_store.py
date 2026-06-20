"""Tests for the per-user store (in-memory path — no Redis needed)."""
import asyncio

from app.services.store import Store


def test_set_get_roundtrip():
    store = Store()  # not connected -> in-memory
    asyncio.run(store.set_json("k", {"a": 1, "b": [1, 2]}))
    assert asyncio.run(store.get_json("k")) == {"a": 1, "b": [1, 2]}


def test_missing_key_returns_none():
    assert asyncio.run(Store().get_json("nope")) is None


def test_defaults_to_memory_without_redis():
    assert Store().backend == "memory"
