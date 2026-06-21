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


def test_redacted_url_never_leaks_password():
    from app.services.store import _redacted

    out = _redacted("redis://default:superSecretPw@my-host.redis.io:13805")
    assert "superSecretPw" not in out  # password stripped
    assert "my-host.redis.io" in out and "13805" in out  # host/port kept for debugging
