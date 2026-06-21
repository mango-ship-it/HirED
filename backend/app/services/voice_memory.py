"""Persistent voice-agent memory (Redis) — the qualified 'agent memory' pattern.

The Deepgram Voice Agent conversation runs browser <-> Deepgram over WebSocket; the
frontend forwards each turn here so the coach REMEMBERS across turns and sessions. On the
next /voice-agent/config we fold the recent history into the agent's system prompt, so the
coach can say "last time you asked about CDL — did you start that course?". Stored in Redis
(durable, survives restarts); degrades to in-memory via the shared store.
"""

from __future__ import annotations

import logging

from app.services.store import get_store

logger = logging.getLogger("hired.voice_memory")

_MAX_TURNS = 40  # keep the last ~20 exchanges
_TTL = 30 * 24 * 3600  # remember a user's coaching history for 30 days
_MAX_CONTENT = 1000  # clip any single turn


def _key(user_id: str) -> str:
    return f"agent:{user_id}:messages"


async def append_turn(user_id: str, role: str, content: str) -> int:
    """Append one {role, content} turn (role normalized to user|assistant). Returns the new
    turn count. ATOMIC (Redis RPUSH+LTRIM+EXPIRE) — concurrent per-turn POSTs can't lose a turn."""
    content = (content or "").strip()
    if not user_id or not content:
        return 0
    role = "user" if role == "user" else "assistant"
    try:
        return await get_store().list_push(
            _key(user_id), {"role": role, "content": content[:_MAX_CONTENT]}, max_len=_MAX_TURNS, ttl=_TTL
        )
    except Exception as exc:
        logger.debug("voice memory store failed (%s)", exc)
        return 0


async def get_turns(user_id: str) -> list[dict]:
    """All remembered turns for a user (oldest first). [] if none / store down."""
    if not user_id:
        return []
    try:
        turns = await get_store().list_range(_key(user_id))
        return [t for t in turns if isinstance(t, dict)]
    except Exception:
        return []


async def clear(user_id: str) -> None:
    try:
        await get_store().delete(_key(user_id))
    except Exception:
        pass


def summarize_for_prompt(turns: list[dict], *, max_turns: int = 6) -> str:
    """A compact recap of the last few turns to inject into the agent's system prompt."""
    if not turns:
        return ""
    recent = turns[-max_turns:]
    lines = [f"{'User' if t.get('role') == 'user' else 'You'}: {t.get('content', '')}" for t in recent]
    return (
        "MEMORY — your recent conversation with this user (oldest first). Refer back to it "
        "naturally so they feel remembered; follow up on what they said they'd do:\n"
        + "\n".join(lines)
    )
