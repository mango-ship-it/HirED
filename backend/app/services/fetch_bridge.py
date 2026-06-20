"""Bridge from FastAPI to the Fetch.ai uAgents via one-shot external queries.

`send_sync_message()` sends a single message to an agent's address and awaits its
reply without standing up a full agent inside the web process. Passing
`response_type=<Model>` returns a decoded, validated Model instance directly — no
manual Envelope / base64 / json.loads handling.

Verified against uagents==0.25.2:
    from uagents.communication import send_sync_message
    reply = await send_sync_message(
        destination=ADDRESS, message=msg, response_type=ResponseModel, timeout=15,
    )
    # `reply` is a ResponseModel on success; a MsgStatus/Envelope on failure.

(`uagents.query.query` still works but is @deprecated in 0.25.x and will be removed;
send_sync_message is what it now delegates to.)
"""

from __future__ import annotations

import logging

from uagents import Model
from uagents.communication import send_sync_message

from app.config import get_settings

logger = logging.getLogger("hired.fetch")


class AgentUnavailableError(RuntimeError):
    """Raised when an agent address is unconfigured or the query fails/times out."""


async def ask_agent(
    address: str,
    message: Model,
    response_type: type[Model],
    *,
    timeout: int = 15,
) -> Model:
    """Send `message` to the uAgent at `address` and return its typed reply.

    Raises AgentUnavailableError on a missing address, timeout, transport error, or
    a non-typed reply, so callers can fall back gracefully instead of returning a 500.
    """
    if not address:
        raise AgentUnavailableError(
            "Agent address not configured. Start the agent and set its address in .env."
        )
    try:
        reply = await send_sync_message(
            destination=address,
            message=message,
            response_type=response_type,
            timeout=timeout,
        )
    except Exception as exc:  # transport / decode errors
        logger.warning("uAgent query to %s failed: %s", address, exc)
        raise AgentUnavailableError(str(exc)) from exc

    if isinstance(reply, response_type):
        return reply
    # On failure send_sync_message returns a MsgStatus/Envelope, not our model type.
    raise AgentUnavailableError(f"Agent returned a non-typed reply: {reply!r}")


def resource_agent_address() -> str:
    return get_settings().resource_agent_address


def benchmark_agent_address() -> str:
    return get_settings().benchmark_agent_address
