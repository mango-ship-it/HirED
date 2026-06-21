"""HirED Career Coach — a Fetch.ai uAgent on Agentverse / ASI:One.

Chat with it on ASI:One; it calls the LIVE HirED backend (Exa + Redis + Claude) and returns
a real readiness score + the top free steps to get there. Fetch.ai is the agentic front door;
the Exa/Redis/Claude engine does the work — it does NOT replace them.

Run:  cd backend && PYTHONPATH=. .venv/bin/python agents/hired_coach_agent.py
Then open the Agentverse "Inspector" link it prints, click Connect, and it's live on ASI:One.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from uuid import uuid4

import httpx
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

# HirED backend (Exa + Redis + Claude). Defaults to your LOCAL backend (fast, no cold start) —
# the agent runs on your machine so it can reach localhost. Set HIRED_BACKEND to the Render URL
# if you want to use the deployed one instead.
BACKEND = os.getenv("HIRED_BACKEND", "http://localhost:8000")

agent = Agent(name="hired_career_coach", port=8011, mailbox=True, seed="hired-career-coach-v1")
chat = Protocol(spec=chat_protocol_spec)


def _role(text: str) -> str:
    """Pull the target role out of a free-text message ('I want to be a Registered Nurse')."""
    m = re.search(
        r"(?:become|be|been|as|for|toward|to be|aiming for)\s+(?:an?\s+)?([A-Za-z][A-Za-z /+-]{2,40})",
        text,
        re.I,
    )
    return (m.group(1).strip().rstrip(".,!?") if m else "this role")[:60]


async def _coach(message: str) -> str:
    """Score the user's message against their target role via the live HirED backend."""
    role = _role(message)
    try:
        async with httpx.AsyncClient(timeout=70) as client:  # generous: Render free tier can cold-start
            resp = await client.post(
                f"{BACKEND}/score",
                data={
                    "user_id": "asi-one-user",
                    "target": json.dumps({"type": "role", "value": role}),
                    "resume_text": message,
                },
            )
        data = resp.json()
    except Exception as exc:
        return f"Sorry — I couldn't reach the HirED engine just now ({exc}). Try again in a moment."

    if "score" not in data:
        return (
            "Tell me your target job and a bit about your experience — e.g. *'I want to be a "
            "Registered Nurse, I'm a CNA with 3 years'* — and I'll score your readiness and the "
            "free steps to get there."
        )

    score = data.get("score")
    steps = [f"• {(l.get('action') or l.get('principle') or '').strip()}" for l in (data.get("lessons") or [])[:3]]
    body = "\n".join(s for s in steps if s.strip("• ")) or "You're in strong shape — keep going!"
    return (
        f"Your readiness for **{role}**: **{score}/100**.\n\n"
        f"Top things to work on next:\n{body}\n\n"
        f"_Powered by HirED — Exa for real free resources, Redis for the leaderboard, Claude for "
        f"the coaching. Want your full free roadmap?_"
    )


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    # Acknowledge so ASI:One knows we got it.
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))
    text = " ".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()
    reply = await _coach(text) if text else "Hi! I'm your HirED career coach. What job are you aiming for?"
    await ctx.send(
        sender,
        ChatMessage(timestamp=datetime.utcnow(), msg_id=uuid4(), content=[TextContent(type="text", text=reply)]),
    )


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass  # nothing to do on inbound acks


agent.include(chat, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
