# HirED — Master Plan

> Single source of truth for the hackathon build. Last updated **2026-06-20**.
> Legend: **[ASSUMPTION]** = my working default pending your confirmation · **[OPEN]** = needs a call (see §12).

---

## 0. Decisions locked (2026-06-20)
- **Profile input is chat-first:** chat / elevator-pitch → resume paste → PDF/DOCX → LinkedIn URL.
- **Target input:** company + role text first (job-description URL = stretch).
- **Agents via Fetch.ai (uAgents):** resource lookup and peer-benchmark each run as a standalone
  **uAgent** (own process, auto-registered on Fetch.ai's Almanac); FastAPI bridges to them with
  `uagents.query()`. See §8.
- **Jobs/LinkedIn via Sai:** **Sai** (Simular's computer-using GUI agent) connects users to live job
  postings, LinkedIn, and applications — it drives real sites/apps in a remote desktop. See §8.
- **Voice via Deepgram:** speech-to-text for a spoken elevator pitch / voice mock-interviews, plus
  **TTS narration** for the slide-based lessons. See §8.
- **Lessons = narrated slides, not Pika video:** lessons + roadmap ship as custom slide cards with
  Deepgram TTS narration (Pika video lessons dropped). See §10.
- **API contract locked in `FRONTEND.md`:** `/score`, `/benchmark`, `/resources` (+ voice) — backend
  implements exactly those shapes (§8).
- **Python backend, 3 processes:** FastAPI + the two uAgents run as separate Python processes; all
  sponsor integrations (Claude, Fetch.ai, Deepgram, Redis, Sai) live server-side.
- **Planning Skill:** built a reusable `plan-feature` Claude Code skill under `.claude/skills/` (see §13).

---

## 1. One-liner
HirED is an AI **career tutor** for first-gen, low-income, and career-transitioning job seekers.
Describe yourself (or upload a resume), pick a target job or school, and get: a compatibility score,
the **1–3 specific gaps that matter most**, **free** resources to close them, a step-by-step roadmap,
and a tailored resume — then **re-score** to watch your number climb.

## 2. Pitch / why it matters
- **The hidden curriculum.** Job hunting has unwritten rules — how to quantify a bullet, what
  recruiters actually weight, how to talk about your work, networking etiquette, salary negotiation.
  Kids with white-collar parents absorb this for free at the dinner table. First-gen and low-income
  students don't get that channel. HirED *teaches* the hidden curriculum.
- **AI displacement.** As AI displaces jobs, people must reinvent themselves and re-enter the market
  fast. HirED is the wraparound coach for that transition.
- **Track fit.** We lean into **education / social impact**, not novelty. The product *teaches*
  (lessons + the *why*) while it *does* (resume + roadmap). Resume generation is the **demo
  mechanic**, education is the **pitch**.

## 3. Target persona
Primary: **a low-income / first-gen job seeker in the US**, often pivoting careers or unfamiliar with
a target industry. Secondary: first-gen college students with no resume yet. For low-income users
especially, **wraparound services** are the key ingredient for economic mobility.

## 4. Career journey model (the product's spine)
Four stages — we meet the user wherever they are and route them forward. This is also the
"step-separation of a person's awareness of their goal": each earlier stage assumes *less* clarity
about the goal.

| # | Stage | User's question | Main obstacles | What HirED gives | Action |
|---|-------|-----------------|----------------|------------------|--------|
| 1 | **Discovery** | "What jobs fit me?" | Doesn't know what's out there / what fits | Role suggestions from background + interests; "what is this job" explainers | Ask · Apply(explore) |
| 2 | **Free upskilling** | "What do I learn, and where for free?" | Skill gaps; cost of learning | Gap → free courses/certs (library, community college, MOOCs), apprenticeships | Write · Apply(learn) |
| 3 | **Interviewing** | "Who's hiring & how do I prep?" | Hidden norms; interview anxiety | Mock-interview lessons, elevator-pitch coaching, who's hiring | Collaborate · Ask |
| 4 | **Onboarding & performing** | "How do I succeed once in?" | Adapting/performing in a new env | Onboarding resources, 30/60/90 guidance | Collaborate |

**Action categories** surfaced on every step: **Collaborate · Apply · Ask · Write.**
Research anchors: *apprenticeships, skills-based hiring, navigating pathways to jobs + wraparound
services, career readiness (NACE).*

## 5. Core user flow
1. **Input (chat-first)** — primary entry is a **chat / elevator-pitch** box: **type or speak** a few
   lines about yourself (voice via **Deepgram**); then paste a **resume**, upload a **PDF/DOCX**, or
   submit a **LinkedIn URL**. Build order: chat → resume → PDF → LinkedIn (voice as an add-on to chat).
2. **Target** — **company + role** text first (job-description URL = stretch); optionally a school/program.
3. **Analyze** — extract a structured profile; parse the target into required skills.
4. **Score** — deterministic compatibility score (§7) + matched/missing skills.
5. **Results screen** — score number; 1–3 specific **lesson cards** (gaps that move the needle); **peer-benchmark percentile** (§6).
6. **Act & learn** — resources + roadmap per gap; tailored resume with reasons.
7. **Re-score loop** — apply suggestions / re-upload → the number visibly moves. **← demo money shot; keep it smooth.**

## 6. Killer feature — "How prepared are you?"
Benchmark the user against **people who already secured that dream job/school**. Output a percentile /
readiness bar: *"You're ahead of 40% of people who landed this role — here's what the top tier has
that you don't."* Makes the score **relative and motivating**, not abstract. The **percentile is
computed by a Fetch.ai benchmark uAgent** (§8); the profiles of people who landed the target
role/school are seeded for the demo and can be enriched live via **Sai** (LinkedIn).

## 7. Scoring (deterministic, not ML)
- **Extract first, score second.** Claude pulls structured data (skills found, # quantified
  achievements, experience, education, clarity signals). Claude does **not** invent the number.
- **Fixed weighted formula** (our code):
  `score = skills_match×0.35 + quantified_achievements×0.25 + experience×0.20 + education×0.10 + clarity×0.10`  *(weights sum to 1.0)*
- **Weights from research, not vibes.** Quantified work + skills-match weighted highest; Schmidt &
  Hunter's meta-analysis shows years-of-experience and education are *weak* predictors of performance —
  most resume tools over-weight the wrong things.
- **Deterministic = trustworthy.** Same input → same score. Fix a gap → the number moves. That's
  what makes the demo land.
- The **percentile** (§6) is computed separately by the Fetch.ai benchmark uAgent — it does not feed
  the score formula.
- *[OPEN] Normalize each term to 0–1:* `skills_match = matched / required` (from parsed target);
  define simple proxies for `quantified_achievements`, `experience`, `clarity`.

## 8. Architecture & stack
- **Frontend:** React + Vite + Tailwind v4  *(Bobby, Chris)* — contract in `FRONTEND.md` (frontend branch).
- **Backend:** FastAPI (**Python**) + Redis  *(Kaden, Inseon)*. Runs as **3 processes**: the FastAPI
  server + the two Fetch.ai uAgents. All sponsor integrations live here.
- **AI:** Claude for extraction / target-parse / lesson-gen (**not** scoring — see §7).
- **Agents (Fetch.ai uAgents):** `resource_agent` (curated free FGLI resources per gap) and
  `benchmark_agent` (peer percentile) run as standalone uAgents; FastAPI bridges via `uagents.query()`.
- **Jobs/LinkedIn (Sai):** Simular's GUI agent connects users to live job postings + LinkedIn and can
  drive applications; also used to enrich benchmark profiles.
- **Voice (Deepgram):** speech-to-text (spoken pitch / mock-interviews) + TTS narration for lessons.
- **Async:** Claude / Deepgram / agent calls aren't instant → Redis cache + queue; run independent
  calls in parallel, dependent ones in order; frontend shows skeleton/loading.
- **Sponsors in play:** Claude (AI) · **Fetch.ai** (uAgents — resources + benchmark) · **Sai**
  (GUI agent — jobs/LinkedIn) · **Deepgram** (voice / TTS) · Redis (cache/queue) · Pika (slide design).

### API contract — LOCKED in `FRONTEND.md` (frontend builds against these shapes)
| Endpoint | Input | Output | Backed by |
|----------|-------|--------|-----------|
| `POST /score` | `{ resume, target }` | `{ score, categories: {…}, lessons: [...] }` | Claude extract + deterministic score (§7) |
| `POST /benchmark` | `{ score, target }` | `{ percentile }` | Fetch.ai `benchmark_agent` via `query()` |
| `POST /resources` | `{ gap_category, context }` | `{ resources: [...] }` | Fetch.ai `resource_agent` via `query()` |
| `POST /narrate` | `{ text }` | `{ audio_url }` | Deepgram TTS (Aura) |
| `POST /transcribe` | audio | `{ text }` | Deepgram STT |

`/score` must be **re-callable** with an edited resume → new result (powers the re-score money-shot loop).
Internally `/score` runs intake/extract → parse target → score → 1–3 lessons (the old
intakeProfile/parseTarget/getReport steps collapse into this single endpoint).

### Fetch.ai uAgents — pattern (sponsor)
Each agent is a real uAgent in its own process (genuine SDK usage, not a disguised function call):

```python
# agents/resource_agent.py
from uagents import Agent, Context, Model

class ResourceRequest(Model):
    gap_category: str
    context: str

class ResourceResponse(Model):
    resources: list[str]

agent = Agent(name="resource_agent", seed="resource_agent_seed", port=8001,
              endpoint=["http://localhost:8001/submit"])

RESOURCE_DB = {"quantified_achievements": ["…"]}  # curated FGLI list

@agent.on_message(model=ResourceRequest, replies=ResourceResponse)
async def handle(ctx: Context, sender: str, msg: ResourceRequest):
    await ctx.send(sender, ResourceResponse(resources=RESOURCE_DB.get(msg.gap_category, [])))

if __name__ == "__main__":
    agent.run()   # auto-registers on the Almanac, prints its agent1q… address
```

FastAPI bridges to it with one call (no manual futures / message-queue plumbing):

```python
# app/services/fetch_bridge.py
from uagents.query import query
from uagents.envelope import Envelope
import json

async def ask_agent(address: str, msg, timeout: int = 15):
    resp = await query(destination=address, message=msg, timeout=timeout)
    return json.loads(resp.decode_payload()) if isinstance(resp, Envelope) else resp
```

**Run setup (3 terminals):** `python agents/resource_agent.py` · `python agents/benchmark_agent.py` ·
`uvicorn app.main:app`. Copy each agent's printed `agent1q…` address into backend config once at
startup. Backend owns this; the frontend has zero knowledge Fetch.ai is involved — it just calls
`/resources` / `/benchmark`. (uAgent registration auto-funds on testnet — no manual key needed.)

### Voice (Deepgram) — sponsor
- **STT:** record audio → Deepgram → transcript → same `/score` intake pipeline (voice = input adapter).
- **TTS (Aura):** `/narrate` returns an audio URL; the frontend plays lessons via `<audio>` and
  auto-advances slides on `onEnded`. **This replaces Pika video lessons** (narrated slides + roadmap).
- **Keys:** store the Deepgram API key in `.env` — never commit it.

### Jobs/LinkedIn (Sai) — sponsor
- **What:** Sai (Simular) is a computer-using GUI agent — it logs into real sites/apps in a remote
  desktop, fills forms, and submits. We use it to **connect users to live job postings + LinkedIn**
  and (stretch) auto-apply behind per-step approval gates.
- **Integration note:** *[OPEN]* Sai is GUI/desktop-first — confirm whether there's a programmatic
  API/handoff or whether it runs as a side workflow feeding data into the backend (§12).

## 9. Team & ownership
- **Frontend / UI-UX:** Bobby, Chris
- **Backend (FastAPI + Fetch.ai uAgents):** Kaden, Inseon
- **Slide design + assets:** Pika · **lesson narration:** Deepgram TTS

## 10. Build plan & TODOs (phased)
Tight clock: Sat 6/20 → Sun 6/21, closing 4–6 PM Sun. **[ASSUMPTION] code freeze ~Sun midday.**
Rule: ship a working **end-to-end thin slice first**, then add breadth.

### Phase 0 — Setup (now)
- [ ] Scaffold `/frontend` (Vite React TS + Tailwind v4) and `/backend` (FastAPI)
- [ ] `.env` + sponsor keys (Claude, Deepgram, Sai; Fetch.ai uAgents auto-fund on testnet — no key); Redis running (docker/local)
- [ ] Lock the API contract + shared types (this doc)

### Phase 1 — Backend thin slice (`POST /score`)
- [ ] **`/score`**: Claude extracts a structured profile from `resume` text + parses `target` → skills, quantified count, exp, edu
- [ ] Scoring formula (pure Python) → `score` + per-category `categories` breakdown
- [ ] 1–3 `lessons` (principle → example → next step); resource list stubbed first
- [ ] `/score` returns `{ score, categories, lessons }` (matches FRONTEND.md)
- [ ] *(next adapters)* resume paste → PDF/DOCX → LinkedIn URL → voice (Deepgram STT)

### Phase 2 — Frontend thin slice
- [ ] **Chat / elevator-pitch input** (primary); resume paste next; PDF drag-drop + LinkedIn URL after
- [ ] Target input field (company + role)
- [ ] Results screen: score number + matched/missing
- [ ] API wrapper (fetch/axios) → FastAPI
- [ ] Loading / skeleton state

### Phase 3 — Education layer
- [ ] 1–3 gap **lesson cards** (the fix + the *why*)
- [ ] Free-resource lookup per gap (courses/certs; library/career-center where possible)
- [ ] Roadmap view (stages 1–4)

### Phase 4 — Money shot
- [ ] Edit a bullet → **re-call `/score`** → old vs new score side-by-side (keep it smooth)
- [ ] **`POST /benchmark`** percentile bar — Fetch.ai `benchmark_agent` via `query()`
- [ ] `tailorResume` (stretch endpoint): tailored resume w/ visible diff + reasons

### Phase 5 — Polish & pitch
- [ ] **Fetch.ai**: `resource_agent` + `benchmark_agent` running as own processes, bridged & demoed (`/resources`, `/benchmark`)
- [ ] **Deepgram**: spoken pitch (STT) + `/narrate` TTS for narrated slide lessons, wired & demoed
- [ ] **Sai**: connect users to live job postings / LinkedIn (stretch: auto-apply with approval gates)
- [ ] Async/parallel Claude + voice + agent calls + Redis caching
- [ ] Demo script + slide deck (Pika design); pitch tied to hidden-curriculum + AI-displacement
- [ ] **Seed demo data** so the live demo never depends on a cold/slow API

### Stretch
- [ ] **Narrated lesson player** — slide cards + Deepgram TTS, auto-advance on audio `onEnded`
- [ ] **Sai auto-apply** to matching roles with per-step approval gates
- [ ] School/program targets · location-personalized resources

## 11. Schedule / logistics
- **Check-in:** 9:00 AM Sat (8:30 if first-timer) — 2nd Floor, Upper Sproul entrance
- **Intro to Hackathons:** 9–10 AM Sat — 3rd Floor, Stephens Room
- **Opening:** 10–11 AM Sat — Wheeler Auditorium
- **Orkes workshop (Inseon):** Sat 6/20, 12–1 PM — 3rd Floor, Stephens Room
- **Closing / winners:** 4–6 PM Sun — Wheeler Auditorium

## 12. Open questions
**Resolved 2026-06-20** (see §0): input method · profile input (chat-first) · Fetch.ai = uAgents
(resource + benchmark) · Sai = jobs/LinkedIn GUI agent · benchmark via Fetch.ai uAgent · lessons =
narrated slides (not Pika video) · API contract locked in `FRONTEND.md` · planning skill (built).

**Still open:**
- **Target type** — jobs only for MVP, or jobs **and** schools? *[ASSUMPTION: jobs only; schools = stretch]*
- **Submission deadline** — actual code-freeze/submit time Sunday?
- **Sai handoff** — programmatic API vs a side workflow feeding the backend? Auto-apply in scope, or
  just surface/connect postings? (§8)
- **Benchmark data** — seeded demo profiles only, or live-enriched via Sai/LinkedIn?

## 13. Planning Skill (`plan-feature`)
A reusable Claude Code skill at `.claude/skills/plan-feature/SKILL.md`. Given any feature/task, it
produces a phased plan in this doc's style: one-line goal → constraints → thin end-to-end slice →
phases with checkbox TODOs + owners → MVP-vs-stretch split → open questions → risks. Invoke by asking
to "plan" or "break down" a feature.
