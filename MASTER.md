# HirED — Master Plan

> Single source of truth for the hackathon build. Last updated **2026-06-20**.
> Legend: **[ASSUMPTION]** = my working default pending your confirmation · **[OPEN]** = needs a call (see §12).

---

## 0. Decisions locked (2026-06-20)
- **Profile input is chat-first:** chat / elevator-pitch → resume paste → PDF/DOCX → LinkedIn URL.
- **Target input:** company + role text first (job-description URL = stretch).
- **Live data via Poke:** job data **and** peer-benchmark profiles are gathered live through Poke's
  API/agent (sponsor integration). ⚠️ Poke's inbound API returns only a *delivery ack*, not the
  answer — getting data back into the app needs a callback webhook or a custom MCP server; use Claude
  (+ BrowserBase) for anything that must be synchronous. See §8.
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
1. **Input (chat-first)** — primary entry is a **chat / elevator-pitch** box (type a few lines about
   yourself); then paste a **resume**, upload a **PDF/DOCX**, or submit a **LinkedIn URL**.
   Build order: chat → resume → PDF → LinkedIn.
2. **Target** — **company + role** text first (job-description URL = stretch); optionally a school/program.
3. **Analyze** — extract a structured profile; parse the target into required skills.
4. **Score** — deterministic compatibility score (§7) + matched/missing skills.
5. **Results screen** — score number; 1–3 specific **lesson cards** (gaps that move the needle); **peer-benchmark percentile** (§6).
6. **Act & learn** — resources + roadmap per gap; tailored resume with reasons.
7. **Re-score loop** — apply suggestions / re-upload → the number visibly moves. **← demo money shot; keep it smooth.**

## 6. Killer feature — "How prepared are you?"
Benchmark the user against **people who already secured that dream job/school**. Output a percentile /
readiness bar: *"You're ahead of 40% of people who landed this role — here's what the top tier has
that you don't."* Makes the score **relative and motivating**, not abstract. **Benchmark profiles are
gathered live via Poke** (§8) — Poke's agent surfaces people who've landed the target role/school.

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
- The **percentile** (§6) is computed separately from Poke-sourced benchmark profiles — it does not
  feed the score formula.
- *[OPEN] Normalize each term to 0–1:* `skills_match = matched / required` (from parsed target);
  define simple proxies for `quantified_achievements`, `experience`, `clarity`.

## 8. Architecture & stack
- **Frontend:** React + Vite + Tailwind v4  *(Bobby, Chris)*
- **Backend:** FastAPI + Redis  *(Kaden, Inseon)*
- **AI:** Claude for extraction / target-parse / lesson-gen (**not** scoring).
- **Async:** AI calls aren't instant → Redis-backed queue; run independent calls in parallel,
  dependent ones in order; frontend shows skeleton/loading.
- **Sponsors in play:** Claude (AI) · Redis (cache/queue) · **Poke** (agentic live data — jobs +
  benchmark) · BrowserBase (scrape job-desc URLs) · Pika (design/video) · Orkes (workflow
  orchestration — Inseon's 12–1 PM workshop) · Sai *[?]*.

### API contract (frontend → FastAPI)
| Endpoint | Input | Output |
|----------|-------|--------|
| `intakeProfile(text \| file \| url)` | chat text / resume paste / PDF·DOCX / LinkedIn URL | structured profile |
| `parseTarget(posting)` | company/role text (or URL, stretch) | role + required skills |
| `getReport(profile, job)` | profile + target | score, matched/missing, 1–3 gap lessons, resources |
| `tailorResume(profile, job)` | profile + target | tailored resume (diff: added/removed + reasons) |

`getReport` must be **re-callable** with updated inputs → same mechanism, new result (powers the re-score loop).

### Poke integration (live data — sponsor)
- **What:** Poke (poke.com, The Interaction Company) is an agentic assistant with web + app
  integrations, reachable by API/MCP. We use it for **live job data** and **peer-benchmark profiles**.
- **Inbound API:** `POST https://poke.com/api/v1/inbound/api-message`, header
  `Authorization: Bearer <V2_KEY>` (create the key in Poke "Kitchen"), body `{"message": "..."}`.
  Store the key in `.env` — never commit it.
- ⚠️ **Gotcha:** the inbound API responds with a *delivery ack* (`{"success": true}`), **not** the
  agent's answer. To get data back into HirED:
  - **(a) Custom MCP server** — register our endpoint at `poke.com/integrations/new` so Poke can call
    HirED tools, or
  - **(b) Callback webhook** — instruct Poke to POST results to a HirED endpoint; UI shows an async
    "gathering…" state.
- **Synchronous fallback:** anything that must resolve inside one request (e.g. scoring) uses Claude
  (+ BrowserBase for a URL) directly; reserve Poke for the agentic/async/notify layer + sponsor credit.

## 9. Team & ownership
- **Frontend / UI-UX:** Bobby, Chris
- **Backend:** Kaden, Inseon
- **Design/video assets:** Pika

## 10. Build plan & TODOs (phased)
Tight clock: Sat 6/20 → Sun 6/21, closing 4–6 PM Sun. **[ASSUMPTION] code freeze ~Sun midday.**
Rule: ship a working **end-to-end thin slice first**, then add breadth.

### Phase 0 — Setup (now)
- [ ] Scaffold `/frontend` (Vite React TS + Tailwind v4) and `/backend` (FastAPI)
- [ ] `.env` + sponsor keys (Claude, Redis, Poke V2, BrowserBase); Redis running (docker/local)
- [ ] Lock the API contract + shared types (this doc)

### Phase 1 — Backend thin slice (end-to-end score)
- [ ] **Profile from chat text** (no file parsing yet): Claude extraction → structured profile (skills, quantified count, exp, edu)
- [ ] `parseTarget`: role + required skills from **company/role text**
- [ ] Scoring formula → score + matched/missing
- [ ] `getReport` returns score + gaps (resources stubbed)
- [ ] *(next adapters)* `intakeProfile`: resume paste → PDF/DOCX → LinkedIn URL

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
- [ ] `tailorResume`: tailored resume w/ visible diff + reasons
- [ ] Re-upload → re-score loop, smooth
- [ ] Peer-benchmark percentile bar — data via **Poke** (set up MCP/callback; Claude fallback)

### Phase 5 — Polish & pitch
- [ ] **Poke**: V2 API key in `.env`; live job-data lookups + MCP/callback wired and demoed
- [ ] Async/parallel AI calls + Redis caching
- [ ] Job-desc **URL** input via BrowserBase (if time)
- [ ] Demo script + slides (Pika); pitch tied to hidden-curriculum + AI-displacement
- [ ] **Seed demo data** so the live demo never depends on a cold/slow API

### Stretch
- [ ] **Video lessons** (Pika / UGC-style tutor) alongside the roadmap
- [ ] School/program targets · location-personalized resources

## 11. Schedule / logistics
- **Check-in:** 9:00 AM Sat (8:30 if first-timer) — 2nd Floor, Upper Sproul entrance
- **Intro to Hackathons:** 9–10 AM Sat — 3rd Floor, Stephens Room
- **Opening:** 10–11 AM Sat — Wheeler Auditorium
- **Orkes workshop (Inseon):** Sat 6/20, 12–1 PM — 3rd Floor, Stephens Room
- **Closing / winners:** 4–6 PM Sun — Wheeler Auditorium

## 12. Open questions
**Resolved 2026-06-20** (see §0): input method (company/role text first) · profile input (chat-first)
· benchmark data (live via Poke) · planning skill (yes — built).

**Still open:**
- **Target type** — jobs only for MVP, or jobs **and** schools? *[ASSUMPTION: jobs only; schools = stretch]*
- **Submission deadline** — actual code-freeze/submit time Sunday?
- **Poke return path** — custom MCP server vs callback webhook for getting data back (§8)?

## 13. Planning Skill (`plan-feature`)
A reusable Claude Code skill at `.claude/skills/plan-feature/SKILL.md`. Given any feature/task, it
produces a phased plan in this doc's style: one-line goal → constraints → thin end-to-end slice →
phases with checkbox TODOs + owners → MVP-vs-stretch split → open questions → risks. Invoke by asking
to "plan" or "break down" a feature.
