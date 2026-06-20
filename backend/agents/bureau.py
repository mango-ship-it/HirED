"""Run BOTH HirED uAgents in a single process via a uAgents Bureau.

Reduces the runtime to 2 processes (this Bureau + the FastAPI server) instead of
3. Each agent keeps its own port and its agent1q... address (derived from its
seed), so the addresses you copy into .env are identical whether you run the
agents standalone (`python agents/resource_agent.py`) or together here.

Run:  python agents/bureau.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python agents/bureau.py` from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uagents import Bureau  # noqa: E402

from agents.benchmark_agent import agent as benchmark_agent  # noqa: E402
from agents.resource_agent import agent as resource_agent  # noqa: E402

# The Bureau serves ALL its agents behind ONE port/endpoint and routes inbound
# messages to the right agent by address. It overwrites each agent's individual
# endpoint with this one (you'll see a warning) — so it MUST have a reachable
# endpoint of its own, or external send_sync_message calls can't find the agents.
# Use a port distinct from the API (8000) and the standalone agent ports (8001/8002).
bureau = Bureau(port=8010, endpoint=["http://127.0.0.1:8010/submit"])
bureau.add(resource_agent)
bureau.add(benchmark_agent)


if __name__ == "__main__":
    bureau.run()
