"""Per-user state store — Redis when available, in-memory otherwise.

Remembers a user's parsed profile/skills by ``user_id`` so the app can recall their
inputs across calls (re-score, return visits, and — later — job-data reinforcement).
Uses Redis if it's reachable at ``REDIS_URL``; otherwise a process-local dict, so it
works with ZERO setup and never crashes a request.

Start real Redis (persistent across restarts) with:  brew services start redis
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.config import get_settings

logger = logging.getLogger("hired.store")

_DEFAULT_TTL = 7 * 24 * 3600  # remember a user for a week


def _redacted(url: str) -> str:
    """Hide credentials in a Redis URL so logs never leak the password."""
    try:
        from urllib.parse import urlsplit

        parts = urlsplit(url)
        port = f":{parts.port}" if parts.port else ""
        return f"{parts.scheme}://{parts.hostname or '?'}{port}"
    except Exception:
        return "redis"


class Store:
    """A tiny async JSON KV store backed by Redis, falling back to memory."""

    def __init__(self) -> None:
        self._redis = None
        self._mem: dict[str, str] = {}

    async def connect(self) -> None:
        """Try Redis; on any failure, quietly use the in-memory dict."""
        url = get_settings().redis_url
        try:
            import redis.asyncio as redis

            client = redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=5,  # remote Redis Cloud + TLS needs > 1s
                socket_timeout=5,
            )
            await client.ping()
            self._redis = client
            logger.info("Store: connected to Redis (%s)", _redacted(url))
        except Exception as exc:  # no server, refused, timeout, bad url, etc.
            self._redis = None
            logger.info("Store: Redis unavailable (%s) — using in-memory store.", exc)

    async def aclose(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def raw(self):
        """The underlying redis client (or None in memory mode) — for ops the KV API doesn't
        wrap (e.g. sorted sets). Callers MUST guard for None and degrade gracefully."""
        return self._redis

    async def set_json(self, key: str, value: Any, ttl: int | None = _DEFAULT_TTL) -> None:
        """ttl=None stores permanently (no expiry)."""
        data = json.dumps(value)
        if self._redis is not None:
            try:
                await self._redis.set(key, data, ex=ttl)
                return
            except Exception as exc:
                logger.warning("Store: Redis set failed (%s); using memory.", exc)
        self._mem[key] = data

    async def get_json(self, key: str) -> Optional[Any]:
        raw: Optional[str] = None
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
            except Exception as exc:
                logger.warning("Store: Redis get failed (%s); using memory.", exc)
        if raw is None:
            raw = self._mem.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def list_push(self, key: str, value: Any, *, max_len: int, ttl: int | None = _DEFAULT_TTL) -> int:
        """Append `value` to a Redis LIST, trim to the last `max_len`, set TTL — ATOMIC via a
        pipeline (no read-modify-write race). Returns the resulting length. Memory fallback is
        a plain list (single-process; no concurrency to race)."""
        data = json.dumps(value)
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.rpush(key, data)
                pipe.ltrim(key, -max_len, -1)
                if ttl is not None:
                    pipe.expire(key, ttl)
                pipe.llen(key)
                results = await pipe.execute()
                return int(results[-1])
            except Exception as exc:
                logger.warning("Store: Redis list_push failed (%s); using memory.", exc)
        items = self._mem_list(key)
        items.append(data)
        del items[:-max_len]
        self._mem[key] = json.dumps(items)
        return len(items)

    async def list_range(self, key: str) -> list[Any]:
        """Return all elements of a Redis LIST (oldest first), JSON-decoded. [] if absent/down."""
        rows: list[str] | None = None
        if self._redis is not None:
            try:
                rows = await self._redis.lrange(key, 0, -1)
            except Exception as exc:
                logger.warning("Store: Redis list_range failed (%s); using memory.", exc)
        if rows is None:
            rows = self._mem_list(key)
        out = []
        for r in rows:
            try:
                out.append(json.loads(r))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    async def delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                await self._redis.delete(key)
            except Exception as exc:
                logger.warning("Store: Redis delete failed (%s); using memory.", exc)
        self._mem.pop(key, None)

    def _mem_list(self, key: str) -> list[str]:
        raw = self._mem.get(key)
        if not raw:
            return []
        try:
            val = json.loads(raw)
            return val if isinstance(val, list) else []
        except json.JSONDecodeError:
            return []


_store = Store()


def get_store() -> Store:
    """Process-wide store (opened in the app lifespan)."""
    return _store


# --- profile helpers: remember a user's parsed resume/skills by user_id ---


def profile_key(user_id: str) -> str:
    return f"profile:{user_id}"


async def save_profile(user_id: str, record: dict) -> None:
    await _store.set_json(profile_key(user_id), record)


async def load_profile(user_id: str) -> Optional[dict]:
    return await _store.get_json(profile_key(user_id))
