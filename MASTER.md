# HirED — Master Plan

> Single source of truth for the hackathon build. Last updated **2026-06-20**.
> Legend: **[ASSUMPTION]** = my working default pending your confirmation · **[OPEN]** = needs a call (see §11).

<!-- NEW: Tagline -->

**Tagline:** _Get your score for your resume and see what your next step is._
The score + roadmap result module is internally branded **NextStep** — this is the "money shot" screen users see after analysis.

<!-- NEW: Brand voice -->

**Brand voice:** reliable and kind. Every surface — loading copy, report language, error states — should read like a coach who's on the user's side, not a cold grading system. Avoid clinical/judgmental phrasing ("you failed to…") in favor of constructive framing ("here's what's missing, and how to close it").

---

## 0. Decisions locked (2026-06-20)

- **Profile input is chat-first:** chat / elevator-pitch → resume paste → PDF/DOCX → LinkedIn URL.
- **Target input:** company + role text first (job-description URL = stretch).
- **Agents via Fetch.ai (uAgents):** resource lookup and peer-benchmark each run as a standalone
  **uAgent** (own process, auto-registered on Fetch.ai's Almanac); FastAPI bridges to them with
  `uagents.query()`. See §7.
- **Jobs/LinkedIn via Sai:** **Sai** (Simular's computer-using GUI agent) connects users to live job
  postings, LinkedIn, and applications — it drives real sites/apps in a remote desktop. See §7.
- **Voice via Deepgram:** speech-to-text for a spoken elevator pitch / voice mock-interviews, plus
  **TTS narration** for the slide-based lessons. See §7.
- **Lessons = narrated slides, not Pika video:** lessons + roadmap ship as custom slide cards with
  Deepgram TTS narration (Pika video lessons dropped). See §9.
- **API contract locked in `FRONTEND.md`:** `/score`, `/benchmark`, `/resources` (+ voice) — backend
  implements exactly those shapes (§7).
- **Python backend, 3 processes:** FastAPI + the two uAgents run as separate Python processes; all
  sponsor integrations (Claude, Fetch.ai, Deepgram, Redis, Sai) live server-side.
- **Planning Skill:** built a reusable `plan-feature` Claude Code skill under `.claude/skills/` (see §12).
- <!-- NEW --> **Benchmark mechanism locked:** the peer-benchmark percentile is computed via
  **scraped JDs → synthetic competitor resumes (with generated avatars) → pairwise 2AFC comparisons
  judged by Claude → ELO aggregation → percentile.** This is the concrete algorithm behind the
  `benchmark_agent` referenced in §0/§6/§7.

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
  students don't get that channel. HirED _teaches_ the hidden curriculum.
- **AI displacement.** As AI displaces jobs, people must reinvent themselves and re-enter the market
  fast. HirED is the wraparound coach for that transition.
- **Track fit.** We lean into **education / social impact**, not novelty. The product _teaches_
  (lessons + the _why_) while it _does_ (resume + roadmap). Resume generation is the **demo
  mechanic**, education is the **pitch**.

## 3. Target persona

Primary: **a low-income / first-gen job seeker in the US**, often pivoting careers or unfamiliar with
a target industry. Secondary: first-gen college students with no resume yet. For low-income users
especially, **wraparound services** are the key ingredient for economic mobility.

## 4. Career journey model (the product's spine)

Four stages — we meet the user wherever they are and route them forward. This is also the
"step-separation of a person's awareness of their goal": each earlier stage assumes _less_ clarity
about the goal.

| #   | Stage                       | User's question                        | Main obstacles                            | What HirED gives                                                              | Action               |
| --- | --------------------------- | -------------------------------------- | ----------------------------------------- | ----------------------------------------------------------------------------- | -------------------- |
| 1   | **Discovery**               | "What jobs fit me?"                    | Doesn't know what's out there / what fits | Role suggestions from background + interests; "what is this job" explainers   | Ask · Apply(explore) |
| 2   | **Free upskilling**         | "What do I learn, and where for free?" | Skill gaps; cost of learning              | Gap → free courses/certs (library, community college, MOOCs), apprenticeships | Write · Apply(learn) |
| 3   | **Interviewing**            | "Who's hiring & how do I prep?"        | Hidden norms; interview anxiety           | Mock-interview lessons, elevator-pitch coaching, who's hiring                 | Collaborate · Ask    |
| 4   | **Onboarding & performing** | "How do I succeed once in?"            | Adapting/performing in a new env          | Onboarding resources, 30/60/90 guidance                                       | Collaborate          |

**Action categories** surfaced on every step: **Collaborate · Apply · Ask · Write.**
Research anchors: _apprenticeships, skills-based hiring, navigating pathways to jobs + wraparound
services, career readiness (NACE)._

## 5. Core user flow

### 5.1 Input phase <!-- NEW: expanded with note fields -->

1. **Resume input (chat UI)** — primary entry is a **chat / elevator-pitch** box: **type or speak**
   a few lines about yourself (voice via **Deepgram**); then attach a **resume**.
   - **[ASSUMPTION]** PDF exported from LinkedIn is the _recommended_ format (cleaner structured
     extraction than arbitrary resume PDFs); plain PDF/DOCX upload and resume paste are also accepted.
   - Build order: chat → resume paste → PDF/DOCX → LinkedIn URL (voice as an add-on to chat).
2. **Strict deadline** — user enters their hard timeline (e.g., "looking for a summer internship next
   year," "graduating this December"). This feeds roadmap pacing (§9 Phase 3) — gaps get sequenced
   against how much runway the user actually has, not a generic timeline.
3. **Job goal / target** — company + role text first (job-description URL = stretch); optionally a
   school/program. Target company is enriched with:
   - **Renown proxy:** LinkedIn follower count of the company page.
   - **Size/stage proxy:** employee count bucket (10k+ ≈ big tech) or funding-stage employee range
     (Series A vs. Series B startup), used as a rough "company tier" signal.
   - **Location.**
   - _(These signals feed the competitor-resume generation in §6 — competitors should look plausible
     for a company of that size/renown/location, not generic.)_

### 5.2 Analyzing phase <!-- NEW -->

Budget **~5 minutes** — it's fine to take this long if it buys a meaningfully more detailed report.
The UI must show **dynamic, evolving status** during this window (not a static spinner), and clearly
**alert the user when the report is ready**. Steps, run largely in parallel where independent:

1. Scrape **5–10 job descriptions** for the target role (LinkedIn).
2. Generate **synthetic "competitor" resumes** — several, each with a **generated avatar image** —
   representing plausible people who'd realistically be competing for the same role. These need to
   feel _real enough to be persuasive_, not like strawmen.
3. **Simulate the competition:** pairwise **2AFC** (two-alternative forced choice — "resume A vs.
   resume B, who's the stronger candidate for this JD?") comparisons between the user's resume and
   each generated competitor, aggregated into an **ELO rating** → converted to a percentile.
4. **LLM-as-judge** makes each 2AFC call (Claude; in-context learning against a recruiter rubric —
   see the **[OPEN]** guideline question below). Token-credit budget from the sponsor should cover this.
5. Frontend polls/streams a **status feed** so the user sees the simulation progressing live
   (e.g., "Comparing you against Candidate 3 of 8…", "Scraping job postings…").
6. **[OPEN — needs research, flagged for Claude]** Who/what authors the **judging guideline/rubric**
   the LLM-judge uses? Working idea: have a **larger Claude model** (e.g., Opus) draft the rubric
   once per target role (via in-context learning from real recruiter signals), then reuse that
   rubric across all 2AFC calls for that session rather than re-deriving it every comparison. See
   the "guideline ideas" thread for options to evaluate before committing.

### 5.3 Report / results phase <!-- NEW: expanded from "Results screen" -->

The report should read like **comments from a recruiter**, not a dry scorecard:

- **Strengths** and **weaknesses**, in plain, kind-but-honest language.
- **Head-to-head framing:** "you beat [competitor type] because X" / "you lost to [competitor type]
  because Y" — makes the ELO simulation legible and motivating instead of abstract.
- **Missing experience/projects**, derived directly from the weakness list (so every weakness maps
  to a concrete, actionable gap — not just "improve your skills").
- **Visual suggestions** _(pick what's feasible in the time budget)_:
  - Radar/spider chart of category scores (skills, quantified impact, experience, education, clarity).
  - Percentile/ELO gauge ("ahead of X% of candidates for this role").
  - Head-to-head bar comparing the user vs. 2–3 representative competitors.
  - Timeline/roadmap visualization for the suggestion phase (§5.4).

#### How the score is computed (deterministic, not ML)

- **Extract first, score second.** Claude pulls structured data (skills found, # quantified
  achievements, experience, education, clarity signals). Claude does **not** invent the number.
- **Fixed weighted formula** (our code):
  `score = skills_match×0.35 + quantified_achievements×0.25 + experience×0.20 + education×0.10 + clarity×0.10` _(weights sum to 1.0)_
- **Weights from research, not vibes.** Quantified work + skills-match weighted highest; Schmidt &
  Hunter's meta-analysis shows years-of-experience and education are _weak_ predictors of performance —
  most resume tools over-weight the wrong things.
- **Deterministic = trustworthy.** Same input → same score. Fix a gap → the number moves. That's
  what makes the demo land.
- The **percentile** (§6) is computed separately via the 2AFC/ELO pipeline — it does not feed
  the score formula.
- _[OPEN] Normalize each term to 0–1:_ `skills_match = matched / required` (from parsed target);
  define simple proxies for `quantified_achievements`, `experience`, `clarity`.

### 5.4 Suggestion / next-step phase <!-- NEW -->

1. **Apply for jobs** — surface live postings (Sai/LinkedIn).
2. **Suggested experience/projects** to close each gap — where possible, anchored to a **real
   LinkedIn profile reference** ("here's someone who closed a similar gap by doing X") so the
   suggestion feels grounded, not generic.
3. **Mentor recommendations** — people scraped from LinkedIn who match the target role/path, framed
   as "reach out to them!" with a short reason why they're a relevant contact.

## 6. Killer feature — "How prepared are you?" <!-- UPDATED: concrete mechanism -->

Benchmark the user against **synthetic peers calibrated to people who'd realistically compete for
that target role** (see §5.2 for the pipeline). Output a percentile / readiness bar: _"You're ahead
of 40% of candidates for this role — here's what the top tier has that you don't."_ Makes the score
**relative and motivating**, not abstract.

Mechanism (this **is** what the Fetch.ai `benchmark_agent` does internally):
**scrape JDs → generate competitor resumes + avatars → 2AFC pairwise comparisons via Claude-as-judge
→ aggregate into ELO → convert to percentile.** Competitor profiles are generated fresh per session
(grounded in the target company's renown/size/location signals from §5.1) rather than a static seed
set, though a **seeded fallback set [ASSUMPTION]** should exist so the demo never depends on a live
scrape/generation succeeding in real time.

## 7. Architecture & stack

- **Frontend:** React + Vite + Tailwind v4 _(Bobby, Chris)_ — contract in `FRONTEND.md` (frontend branch).
- **Backend:** FastAPI (**Python**) + Redis _(Kaden, Inseon)_. Runs as **3 processes**: the FastAPI
  server + the two Fetch.ai uAgents. All sponsor integrations live here.
- **AI:** Claude for extraction / target-parse / lesson-gen / 2AFC judging (**not** the deterministic
  score — see §5.3). <!-- NEW --> A **larger Claude model** is used once per session to draft the
  judging rubric consumed by the (likely smaller/faster) judge calls — see §5.2 **[OPEN]**.
- **Agents (Fetch.ai uAgents):** `resource_agent` (curated free FGLI resources per gap) and
  `benchmark_agent` (peer percentile — implements the §6 scrape→generate→2AFC→ELO pipeline) run as
  standalone uAgents; FastAPI bridges via `uagents.query()`.
- **Jobs/LinkedIn (Sai):** Simular's GUI agent connects users to live job postings + LinkedIn and can
  drive applications; also used to scrape JDs (§5.2), enrich benchmark profiles, and source mentor
  recommendations (§5.4).
- **Voice (Deepgram):** speech-to-text (spoken pitch / mock-interviews) + TTS narration for lessons.
- **Avatar images:** <!-- NEW --> **[OPEN]** which image-gen service backs the synthetic competitor
  avatars in §5.2 — needs a sponsor/tool decision before Phase 4.
- **Live status during analysis:** <!-- NEW --> **[OPEN]** mechanism for the ~5-min dynamic status
  feed in §5.2 — candidates: polling a Redis-backed job-status key, Server-Sent Events, or a
  WebSocket. Given Redis is already in the stack, **[ASSUMPTION]** lean toward polling a
  `/score/status` (or `/benchmark/status`) endpoint backed by Redis unless someone wants to build SSE.
- **Async:** Claude / Deepgram / agent calls aren't instant → Redis cache + queue; run independent
  calls in parallel, dependent ones in order; frontend shows skeleton/loading.
- **Sponsors in play:** Claude (AI) · **Fetch.ai** (uAgents — resources + benchmark) · **Sai**
  (GUI agent — jobs/LinkedIn/JD scraping/mentor sourcing) · **Deepgram** (voice / TTS) · Redis
  (cache/queue) · Pika (slide design) · _(avatar image-gen — TBD)_.

### API contract — LOCKED in `FRONTEND.md` (frontend builds against these shapes)

| Endpoint                | Input                       | Output                                       | Backed by                                                  |
| ----------------------- | --------------------------- | -------------------------------------------- | ---------------------------------------------------------- |
| `POST /score`           | `{ resume, target }`        | `{ score, categories: {…}, lessons: [...] }` | Claude extract + deterministic score (§5.3)                 |
| `POST /benchmark`       | `{ score, target }`         | `{ percentile }`                             | Fetch.ai `benchmark_agent` — scrape→generate→2AFC→ELO (§6) |
| `POST /resources`       | `{ gap_category, context }` | `{ resources: [...] }`                       | Fetch.ai `resource_agent` via `query()`                    |
| `POST /narrate`         | `{ text }`                  | `{ audio_url }`                              | Deepgram TTS (Aura)                                        |
| `POST /transcribe`      | audio                       | `{ text }`                                   | Deepgram STT                                               |
| `GET /benchmark/status` | —                           | `{ stage, progress, message }`               | Redis job status _(new — see §7 status mechanism)_         |

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
  desktop, fills forms, and submits. We use it to **connect users to live job postings + LinkedIn**,
  **scrape JDs for the benchmark pipeline (§6)**, **source mentor recommendations (§5.4)**, and
  (stretch) auto-apply behind per-step approval gates.
- **Integration note:** _[OPEN]_ Sai is GUI/desktop-first — confirm whether there's a programmatic
  API/handoff or whether it runs as a side workflow feeding data into the backend (§11).

## 8. Team & ownership

- **Frontend / UI-UX:** Bobby, Chris
- **Backend (FastAPI + Fetch.ai uAgents):** Kaden, Inseon
- **Slide design + assets:** Pika · **lesson narration:** Deepgram TTS

## 9. Build plan & TODOs (phased)

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
- [ ] _(next adapters)_ resume paste → PDF/DOCX → LinkedIn URL → voice (Deepgram STT)
- [ ] <!-- NEW --> Add `deadline` + target `company info` (followers / size-stage bucket / location) to the intake schema

### Phase 2 — Frontend thin slice

- [ ] **Chat / elevator-pitch input** (primary); resume paste next; PDF drag-drop + LinkedIn URL after
- [ ] Target input field (company + role) <!-- NEW --> + deadline field + company-info auto-lookup display
- [ ] Results screen: score number + matched/missing
- [ ] API wrapper (fetch/axios) → FastAPI
- [ ] Loading / skeleton state <!-- NEW --> → evolve into the dynamic ~5-min status feed (§5.2/§7)

### Phase 3 — Education layer

- [ ] 1–3 gap **lesson cards** (the fix + the _why_)
- [ ] Free-resource lookup per gap (courses/certs; library/career-center where possible)
- [ ] Roadmap view (stages 1–4), paced against the user's **strict deadline**
- [ ] <!-- NEW --> Suggested experience/projects per gap, anchored to a real LinkedIn profile reference where possible
- [ ] <!-- NEW --> Mentor recommendation cards (sourced via Sai/LinkedIn)

### Phase 4 — Money shot

- [ ] Edit a bullet → **re-call `/score`** → old vs new score side-by-side (keep it smooth)
- [ ] **`POST /benchmark`** — scrape JDs → generate competitor resumes + avatars → 2AFC via Claude-judge → ELO → percentile bar
- [ ] **`GET /benchmark/status`** — dynamic status feed for the analyzing UI
- [ ] Report content: strengths/weaknesses, head-to-head "beat/lost to" call-outs, missing experience tied to weaknesses
- [ ] `tailorResume` (stretch endpoint): tailored resume w/ visible diff + reasons

### Phase 5 — Polish & pitch

- [ ] **Fetch.ai**: `resource_agent` + `benchmark_agent` running as own processes, bridged & demoed (`/resources`, `/benchmark`)
- [ ] **Deepgram**: spoken pitch (STT) + `/narrate` TTS for narrated slide lessons, wired & demoed
- [ ] **Sai**: connect users to live job postings / LinkedIn / JD scraping / mentor sourcing (stretch: auto-apply with approval gates)
- [ ] Async/parallel Claude + voice + agent calls + Redis caching
- [ ] Report visuals: radar chart, ELO/percentile gauge, head-to-head bar, roadmap timeline
- [ ] Demo script + slide deck (Pika design); pitch tied to hidden-curriculum + AI-displacement
- [ ] **Seed demo data** (incl. a seeded competitor-resume set, §6) so the live demo never depends on a cold/slow scrape or generation

### Stretch

- [ ] **Narrated lesson player** — slide cards + Deepgram TTS, auto-advance on audio `onEnded`
- [ ] **Sai auto-apply** to matching roles with per-step approval gates
- [ ] School/program targets · location-personalized resources

## 10. Schedule / logistics

- **Check-in:** 9:00 AM Sat (8:30 if first-timer) — 2nd Floor, Upper Sproul entrance
- **Intro to Hackathons:** 9–10 AM Sat — 3rd Floor, Stephens Room
- **Opening:** 10–11 AM Sat — Wheeler Auditorium
- **Orkes workshop (Inseon):** Sat 6/20, 12–1 PM — 3rd Floor, Stephens Room
- **Closing / winners:** 4–6 PM Sun — Wheeler Auditorium

## 11. Open questions

**Resolved 2026-06-20** (see §0): input method · profile input (chat-first) · Fetch.ai = uAgents
(resource + benchmark) · Sai = jobs/LinkedIn GUI agent · benchmark via Fetch.ai uAgent · lessons =
narrated slides (not Pika video) · API contract locked in `FRONTEND.md` · planning skill (built) ·
benchmark mechanism = scrape→generate→2AFC→ELO (§0/§6).

**Still open:**

- **Target type** — jobs only for MVP, or jobs **and** schools? _[ASSUMPTION: jobs only; schools = stretch]_
- **Submission deadline** — actual code-freeze/submit time Sunday?
- **Sai handoff** — programmatic API vs a side workflow feeding the backend? Auto-apply in scope, or
  just surface/connect postings? (§7)
- **Benchmark data** — fully live scrape+generate each session, or seeded demo profiles with live
  enrichment as a fallback? _[ASSUMPTION: seeded fallback always present, §6]_
- <!-- NEW --> **Judging-rubric authorship** — what does the larger-Claude-model-authored guideline
  for the LLM-judge actually contain, and is it regenerated per session or per target role? Needs
  research before Phase 4 (§5.2).
- <!-- NEW --> **Avatar image generation** — which tool/sponsor for the competitor avatars (§7)?
- <!-- NEW --> **Status-feed transport** — polling vs SSE vs WebSocket for the ~5-min analyzing UI (§7)?
- <!-- NEW --> **Mentor scraping** — any LinkedIn ToS / consent consideration before surfacing scraped
  profiles as "reach out to them" suggestions (§5.4)? Worth a quick check even for demo purposes.

## 12. Planning Skill (`plan-feature`)

A reusable Claude Code skill at `.claude/skills/plan-feature/SKILL.md`. Given any feature/task, it
produces a phased plan in this doc's style: one-line goal → constraints → thin end-to-end slice →
phases with checkbox TODOs + owners → MVP-vs-stretch split → open questions → risks. Invoke by asking
to "plan" or "break down" a feature.
