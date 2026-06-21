# Design: fetch.ai Resource Multi-Agent Architecture

**Date:** 2026-06-21
**Status:** Approved
**Scope:** `backend/agents/` — resource agent pipeline only

---

## Problem

The current `resource_agent` returns resources by broad gap category (`skills_match`, `experience`, etc.) from a static lookup. A user missing "React" and "SQL" gets the same generic freeCodeCamp link as a user missing "Docker" and "Kubernetes." Resources are not specific to what the user actually lacks.

## Goal

Make resource recommendations specific to the user's **actual missing skills** by name, while keeping the FastAPI contract unchanged and leveraging fetch.ai's native agent-to-agent messaging.

---

## Architecture

```
FastAPI
  └─ resource_coordinator_agent   (port 8001, replaces resource_agent)
        ├─ skills_resource_agent       (port 8003)
        ├─ experience_resource_agent   (port 8004)
        ├─ education_resource_agent    (port 8005)
        ├─ clarity_resource_agent      (port 8006)
        └─ quantified_resource_agent   (port 8007)
```

FastAPI never changes: it still calls one address and gets `ResourceResponse`. The coordinator owns the fan-out internally.

---

## Components

### `agents/messages.py` — message model changes

```python
class ResourceRequest(Model):
    gap_category: str
    context: str = ""
    missing_skills: list[str] = []   # NEW — specific skill names from the score pipeline

class SkillResourceRequest(Model):   # NEW — internal agent-to-agent only
    skill: str

class SkillResourceResponse(Model):  # NEW — internal agent-to-agent only
    resources: list[ResourceItem]

# ResourceResponse shape unchanged — no FastAPI contract break
class ResourceResponse(Model):
    resources: list[ResourceItem]
```

### `agents/resource_coordinator_agent.py` — replaces `resource_agent.py`

- Receives `ResourceRequest` from FastAPI via `@on_query`
- Maps each skill in `missing_skills` to the appropriate specialist agent address using `CATEGORY_MAP` (skill name → agent env var)
- Fans out `SkillResourceRequest` to each specialist via `ctx.send()`
- Collects `SkillResourceResponse` replies using asyncio events with a **3-second timeout per specialist**
- Falls back to existing static `RESOURCE_DB[gap_category]` for any specialist that times out
- Deduplicates by URL, caps output at 6 items, returns `ResourceResponse`

### `agents/skills_resource_agent.py`

Owns a skill-level DB keyed by individual skill name (React, SQL, Python, TypeScript, Docker, etc.). Returns the 2–3 best free resources for each named skill. Handles the catch-all for unknown skill names.

### `agents/experience_resource_agent.py`

Owns experience-gap resources: micro-internships (Parker Dewey), skilled volunteering (Catchafire), beginner open-source issues (Up For Grabs), etc.

### `agents/education_resource_agent.py`

Owns education-gap resources: Khan Academy, Google Career Certificates, CLEP exams, community college programs.

### `agents/clarity_resource_agent.py`

Owns clarity/communication resources: Hemingway Editor, Purdue OWL, MIT CAPD action verbs list.

### `agents/quantified_resource_agent.py`

Owns quantified-achievement resources: XYZ bullet formula, resume bullet workshops, Handshake guides.

### `agents/bureau.py` — updated

Runs all 6 agents (coordinator + 5 specialists) in one `Bureau` process alongside the existing `benchmark_agent`.

---

## Data Flow

```
1. POST /resources  { gap_category: "skills_match", missing_skills: ["React", "SQL"] }
        │
2. fetch_bridge.ask_agent(RESOURCE_COORDINATOR_ADDRESS, ResourceRequest(...))
        │
3. coordinator @on_query fires
        ├─ maps "React" → skills_resource_agent  → ctx.send(SkillResourceRequest(skill="React"))
        ├─ maps "SQL"   → skills_resource_agent  → ctx.send(SkillResourceRequest(skill="SQL"))
        │   (one ctx.send per skill; same specialist receives both)
        │
4. skills_resource_agent @on_message fires twice (once per skill)
        └─ returns SkillResourceResponse for "React", then for "SQL"
        │
5. coordinator receives reply, aggregates, deduplicates by URL, caps at 6
        └─ returns ResourceResponse to FastAPI
        │
6. /resources returns { resources: [...] }  ← same shape as before
```

---

## Fallback Chain

| Failure | Behavior |
|---|---|
| Specialist doesn't reply within 3s | Coordinator uses `RESOURCE_DB[gap_category]` for that domain |
| Coordinator unreachable | `fetch_bridge` raises `AgentUnavailableError` → route returns static fallback, no 500 |
| `missing_skills` is empty | Coordinator routes by `gap_category` only (backward compatible) |
| Unknown skill name | Routes to `skills_resource_agent` as catch-all |

---

## Environment Variables

Six new addresses in `backend/.env` (printed on bureau startup, stable across restarts via seed):

```
RESOURCE_COORDINATOR_ADDRESS=agent1q...
SKILLS_RESOURCE_AGENT_ADDRESS=agent1q...
EXPERIENCE_RESOURCE_AGENT_ADDRESS=agent1q...
EDUCATION_RESOURCE_AGENT_ADDRESS=agent1q...
CLARITY_RESOURCE_AGENT_ADDRESS=agent1q...
QUANTIFIED_RESOURCE_AGENT_ADDRESS=agent1q...
```

`RESOURCE_AGENT_ADDRESS` is deprecated and can be removed once coordinator is live.

---

## FastAPI Changes

- `app/services/fetch_bridge.py`: `resource_agent_address()` → `resource_coordinator_address()`, reads `RESOURCE_COORDINATOR_ADDRESS`
- `app/routes/agents.py`: pass `missing_skills` from the stored profile into `ResourceRequest`
- `/health` endpoint: report all 6 resource agents as up/down

---

## Running Locally

```bash
# Terminal 1 — all agents
python agents/bureau.py

# Terminal 2 — FastAPI
uvicorn app.main:app --reload
```

Bureau prints each `agent1q…` address on startup. Copy into `.env` once (addresses are stable via seed).

---

## Testing

- **Unit:** each specialist agent's lookup for known skill names
- **Integration:** start bureau, call coordinator via `send_sync_message`, assert skill-specific resources returned
- **Fallback:** configure coordinator with invalid specialist address, assert static fallback returned without error

---

## Out of Scope

- Live web search for resources (static DB only)
- Claude-generated recommendations inside agents
- Changes to `benchmark_agent` or the scoring pipeline
- Changes to the FastAPI `/resources` response contract
