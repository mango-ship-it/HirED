# HirED Backend

FastAPI backend for HirED — an AI career tutor. Implements the locked API contract
(`FRONTEND.md`) and wires up the sponsor integrations: **Claude** (extraction +
lessons), **Fetch.ai uAgents** (resources + benchmark), **Deepgram** (voice).

## Runtime

**Pin Python 3.12.** The local default is 3.14.5, which works for the pure-Python
stack but is risky for `uagents` (it pulls in `cosmpy` → `protobuf<6` + native
`pynacl`/`bcrypt`/`grpcio` wheels, where 3.14 coverage still lags). A `.venv` on
3.12 is already set up.

```bash
cd backend
python3.12 -m venv .venv          # already present
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then fill in keys
```

## API contract (LOCKED — do not change shapes)

| Endpoint           | Input                                               | Output                                                                | Backed by                              |
|--------------------|-----------------------------------------------------|-----------------------------------------------------------------------|----------------------------------------|
| `POST /score`      | multipart: `user_id`, `target`, `resume_file`/`resume_text` | `{score, categories, lessons, matched_skills, missing_skills, status}` | extract (Claude/heuristic) + scorer    |
| `POST /benchmark`  | `{user_id, score, target}`                          | `{percentile, sample_size, message}`                                  | Fetch.ai benchmark agent (+fallback)   |
| `POST /resources`  | `{user_id, gap_category, context}`                  | `{resources:[{name,url,description}]}`                                 | Fetch.ai resource agent (+fallback)    |
| `POST /report`     | scored data + `target`                              | `{summary, strengths, weaknesses, next_steps, jobs, mentors, slides}` | templated (free) + Sai jobs/mentors    |
| `POST /narrate`    | `{text}`                                             | `{audio_url}`                                                         | Deepgram TTS (cached by text)          |
| `POST /transcribe` | audio file (multipart)                              | `{text}`                                                              | Deepgram STT (Nova)                    |

`/score`'s `categories` are keyed by snake_case category (`skills_match`, …) with
`{score, weight}` each. **`API_CONTRACT.md` (repo root) is the authoritative
frontend/backend contract.**

## Scoring (deterministic, NOT an LLM number — MASTER.md §7)

```
score = skills_match*0.35 + quantified_achievements*0.25
      + experience*0.20 + education*0.10 + clarity*0.10
```

Each term is normalized to 0..1 in `app/scoring.py` (`skills_match = matched /
required`). Same input → same score; fix a gap → the number moves (the re-score
money shot). Claude extracts the raw signals; it never invents the number.

## Pipeline & pluggable scoring

`/score` runs three stages — only the middle one is Claude:

1. **Parse** (`services/document_parser.py`): file (PDF/DOCX/RTF/TXT) → text.
2. **Extract** (`services/extractor.py`): text → structured signals. Uses **Claude**
   when `ANTHROPIC_API_KEY` is set, else a dependency-free **heuristic**
   (`heuristic_extractor.py`). **So `/score` works with no key** — the frontend can
   integrate immediately; quality upgrades automatically once the key is added.
3. **Score** (`services/scoring_engine.py`): signals → number + categories.
   **Pluggable** — default is the deterministic formula above; a teammate's scorer
   drops in via one env var.

### Plug in a custom scorer

Create `app/services/custom_scorer.py`:

```python
from app.services.scoring_engine import CategoryScore, ScoreOutcome

class CustomScorer:
    name = "custom"
    async def score(self, *, profile, resume, target) -> ScoreOutcome:
        # ...your model / formula... Return the FIVE snake_case contract categories
        # so the frontend bars + "what the top tier has" chips keep working:
        return ScoreOutcome(score=72, categories={
            "skills_match":            CategoryScore(score=65, weight=0.35),
            "quantified_achievements": CategoryScore(score=40, weight=0.25),
            "experience":              CategoryScore(score=80, weight=0.20),
            "education":               CategoryScore(score=90, weight=0.10),
            "clarity":                 CategoryScore(score=70, weight=0.10),
        })
```

Then set `SCORER=custom` in `.env`. No route or contract changes. An unknown or
broken scorer logs and falls back to deterministic — the page never breaks.

## Live LinkedIn data via Sai (pysimular) — optional

Sai (Simular) is a macOS app driven by the `pysimular` client. Because `run()` blocks
on a Cocoa run loop for minutes, it can't live in the API — instead a small worker
produces a JSON file the backend reads (`SAI_DATA_PATH`). A demo **seed ships**, so
jobs/mentors work with zero setup.

To wire real LinkedIn data (macOS only):

```bash
# 1. Install the app: open simular-mac-agent-*.dmg -> ~/Applications, launch, sign in to LinkedIn
# 2. Install the optional client (kept out of core requirements.txt):
pip install -r requirements-sai.txt
# 3. Fetch jobs + mentors for a target:
python scripts/sai_fetch.py "Marketing Coordinator" --out app/data/sai_live.json
# 4. Point the backend at it in backend/.env:
#    SAI_DATA_PATH=app/data/sai_live.json
```

## Run (MASTER.md §8)

```bash
# Terminal 1 — resource uAgent (prints its agent1q... address on startup)
python agents/resource_agent.py

# Terminal 2 — benchmark uAgent (prints its agent1q... address)
python agents/benchmark_agent.py

# Copy both printed addresses into .env (RESOURCE_AGENT_ADDRESS,
# BENCHMARK_AGENT_ADDRESS), then:

# Terminal 3 — API
uvicorn app.main:app --reload
```

**Fewer processes:** run both agents in one process with a Bureau instead of
Terminals 1–2 (the `agent1q…` addresses are unchanged — they derive from each
agent's seed):

```bash
python agents/bureau.py        # both uAgents in one process (prints both addresses)
uvicorn app.main:app --reload  # the API
```

If an agent isn't running, `/benchmark` and `/resources` return graceful local
fallbacks so a live demo never hard-fails on a cold agent.

## Test

```bash
pytest -q              # deterministic scoring is fully covered (no network)
```

## Layout

```
app/
  main.py               FastAPI app, CORS, /static mount, /health
  config.py             env-driven settings (pydantic-settings)
  scoring.py            deterministic scorer (pure, TDD-covered)
  models/
    schemas.py          request/response schemas (the locked contract)
    extraction.py       ExtractedProfile + JSON schema fed to Claude
  routes/
    score.py            POST /score
    agents.py           POST /benchmark, POST /resources
    voice.py            POST /narrate, POST /transcribe
  services/
    claude_service.py   Anthropic: extraction + lesson generation
    deepgram_service.py Deepgram: TTS + STT
    fetch_bridge.py     send_sync_message() bridge to the agents
    profile_signals.py  ExtractedProfile -> scorer signals adapter
agents/
  messages.py           shared uAgent Models
  resource_agent.py     Fetch.ai resource uAgent (own process)
  benchmark_agent.py    Fetch.ai benchmark uAgent (own process)
  bureau.py             run both uAgents in one process (optional)
tests/
  test_scoring.py       scoring spec (TDD)
  test_api_smoke.py     contract + fallback smoke (no network)
```
