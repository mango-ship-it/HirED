# BACKEND.md — HirED API & data design

> The backend's authoritative spec. Pairs with **FRONTEND.md** (the frontend mocks these shapes)
> and **MASTER.md** (§7 scoring, §8 stack). Stack: **FastAPI (Python)** + Redis, running as **3
> processes** (FastAPI server + the two Fetch.ai uAgents). Last updated **2026-06-20**.
> Legend: **[LOCKED]** = shape is frozen in FRONTEND.md, do not change · **[ADD]** = additive,
> backward-compatible, confirm with frontend before relying on it · **[STRETCH]** = post-MVP.

---

## 0. Design principles
1. **Frontend never touches a sponsor directly.** The backend is the only thing that holds API keys
   and talks to Claude / Fetch.ai / Deepgram / Sai. The frontend only ever calls our REST endpoints
   and renders whatever JSON comes back (FRONTEND.md echoes this).
2. **Locked shapes stay locked.** `/score`, `/benchmark`, `/resources` keep the exact request/response
   fields from FRONTEND.md. Every new field is **additive** (frontend can ignore it) and flagged `[ADD]`.
3. **Two response styles, always loadable.**
   - **Synchronous** (seconds): `/score`, `/resources`, `/benchmark`, `/transcribe` — return the answer directly.
   - **Async job** (tens of seconds): `/presentation`, `/jobs/search` — return `{ id, status: "pending" }`
     immediately, frontend polls a `GET`. AI/agent/render work isn't instant; never make the UI guess.
4. **Stateful where it pays for itself.** Identifiers (§1) let us re-score, version resumes, and let the
   summary/report page fetch everything from one run with a single id.
5. **Deterministic score (MASTER.md §7).** Claude *extracts signals*; our pure-Python `scoring.py`
   *computes the number*. Same signals in → same score out — that's what makes the re-score demo land.

---

## 1. Identifiers & state — *do we need a `document_id`?*

**Yes — add `document_id`, and also `session_id`.** They answer two different questions:

| Id | Scope | Created by | Answers | MVP store |
|----|-------|-----------|---------|-----------|
| `session_id` | One analysis **run** (one resume × one target, at a moment) | `POST /score` | "Give me everything produced by this run" (score, benchmark, lessons, slides, report) | Redis hash, TTL |
| `document_id` | One stored **resume/profile**, across runs | `POST /documents` or first `/score` | "Track this resume over time / re-score the edited version / don't re-upload" | Redis hash, TTL |
| `version` (int) | One **edit** of a document | each edit/re-upload/re-score | Old-vs-new diff for the money-shot | under the document |
| `presentation_id`, `report_id`, `audio_id` | One generated **artifact** | the endpoint that makes it | "Fetch / re-show this output later" | Redis + `static/` |

**Why `document_id` specifically (your "keep track of resumes" question):**
- The **re-score money shot** needs *old vs new*. We store each edit as a new `version` under the same
  `document_id`, so `/score` can return both the new score and the previous version's score to diff.
- Avoids re-uploading + re-parsing a PDF on every call (parse once, reference by id).
- Future-proofs: a user's resume history, or scoring the *same* resume against *multiple* targets.

**Phasing:** MVP keeps all of this in **Redis with a TTL** (opaque UUID strings, no real DB needed). Later,
swap the store for Postgres **without changing the contract** — the ids are already opaque. So the
`document_id` field costs us nothing now and unlocks persistence later.

---

## 2. Endpoint reference

### Group A — Core analysis loop *(locked + additive)*

**`POST /score`** — the spine. Chat/resume + target → score, breakdown, lessons. Re-callable.
```jsonc
// request
{
  "resume": "string",        // [LOCKED] raw resume / chat / elevator-pitch text
  "target": "string",        // [LOCKED] dream job/school text or pasted posting
  "document_id": "string?",  // [ADD] reference a stored doc instead of re-sending text
  "session_id": "string?"    // [ADD] re-score within an existing run lineage
}
// response
{
  "score": 0,                // [LOCKED] 0–100, deterministic (scoring.py)
  "categories": {            // [LOCKED] per-skill breakdown, human labels
    "Skills Match":        { "score": 0, "weight": 0.35, "contribution": 0.0 },
    "Quantified Impact":   { "score": 0, "weight": 0.25, "contribution": 0.0 },
    "Relevant Experience": { "score": 0, "weight": 0.20, "contribution": 0.0 },
    "Education":           { "score": 0, "weight": 0.10, "contribution": 0.0 },
    "Clarity & Communication": { "score": 0, "weight": 0.10, "contribution": 0.0 }
  },
  "lessons": [ /* Lesson, §3 */ ],   // [LOCKED] 1–3 gap lessons
  "session_id": "string",            // [ADD]
  "document_id": "string",           // [ADD]
  "version": 1,                       // [ADD]
  "previous_score": 0,                // [ADD] present on a re-score → drives old-vs-new
  "gaps": [ /* Gap, §3 */ ],          // [ADD]
  "profile": { /* Profile, §3 */ },   // [ADD] what Claude extracted (debug/transparency)
  "target_parsed": { /* Target, §3 */ } // [ADD]
}
```
Backed by: **Claude** (extract profile + parse target) → **scoring.py** (number) → **Claude** (lessons).
Cache key: `sha256(resume + target)`.

**`POST /benchmark`** — peer percentile.
```jsonc
// request
{ "score": 0, "target": "string", "session_id": "string?" }   // score+target [LOCKED]
// response
{
  "percentile": 0,                 // [LOCKED] 0–100 "ahead of N% who landed this"
  "cohort_size": 0,                // [ADD]
  "comparison": {                  // [ADD] the "different skillsets you'd use" view
    "you": ["python","sql"],
    "top_tier": ["python","sql","airflow","dbt"],
    "add_these": ["airflow","dbt"]
  }
}
```
Backed by: **Fetch.ai `benchmark_agent`** via `query()`; cohort seeded for demo, enrichable via **Sai**.

**`POST /resources`** — free resources for one gap.
```jsonc
// request
{ "gap_category": "string", "context": "string" }   // [LOCKED]
// response
{ "resources": [ /* Resource, §3 */ ] }              // [LOCKED] key name; see item-shape note
```
Backed by: **Fetch.ai `resource_agent`** via `query()`.
> ⚠️ **Item shape — confirm with frontend.** The uAgent quickstart returns `list[str]`. Richer cards
> (`{label,url,provider,cost}`) are far more useful for the resource slide. Recommend objects with a
> `label` string so a string-expecting frontend still renders. This is the one likely contract edit — lock it on hour 1.

### Group B — Documents *(resume tracking, §1)* `[ADD]`
- **`POST /documents`** — `multipart file (PDF/DOCX)` **or** `{ "text": "...", "kind": "resume" }`
  → `{ "document_id", "version", "kind", "parsed_text", "char_count" }`. Parse once, reference later.
- **`GET /documents/{document_id}`** → `{ document_id, kind, latest_version, versions: [{version, created_at, char_count, score?}] }`.
- Backed by: **pypdf/python-docx** (text extraction) + optional **Claude** cleanup.

### Group C — Voice (Deepgram)
- **`POST /transcribe`** — `multipart audio` → `{ "text", "duration_s"?, "confidence"? }`. Spoken pitch →
  text → feeds `/score` or `/documents`. Voice is an **input adapter**, not a separate pipeline.
- **`POST /narrate`** `[ADD]` — `{ "text", "voice"?, "session_id"? }` → `{ "audio_id", "audio_url" }`.
  Writes an mp3 to `backend/static/audio/{audio_id}.mp3` (gitignored) served at `/static/audio/...`.
- Backed by: **Deepgram** STT (nova) + TTS (Aura).

### Group D — Presentation / slides *(async)* `[ADD]`
- **`POST /presentation`** — `{ "session_id" }` → `{ "presentation_id", "status": "pending" }`. Enqueues a job.
- **`GET /presentation/{presentation_id}`** → `{ "status": "pending|ready|error", "slides": [ /* Slide, §3 */ ], "video_url"?, "error"? }`.
- Backed by: **Claude** (slide copy + speaker notes from the run) → **Deepgram** (per-slide TTS) →
  **Pika** (background visuals) → assembled narrated deck. **This is the "video presentation or slides."**

### Group E — Summary / Report *(the third / landing page)* `[ADD]`
- **`GET /report/{session_id}`** → the whole summary page in one payload:
  ```jsonc
  {
    "session_id", "document_id", "generated_at",
    "score", "categories", "percentile", "comparison",
    "gaps", "lessons", "resources",
    "roadmap": [ /* stages 1–4, MASTER.md §4 */ ],
    "next_steps": ["...", "..."],
    "summary_text": "narrative recap (Claude)",
    "presentation_id": "string?"
  }
  ```
- **`GET /sessions/{session_id}`** — the generic **"surface anything"** index: status + which artifacts
  exist + their ids/links. Frontend hits this to know what's ready.
  ```jsonc
  { "session_id", "status", "score": 0, "has_benchmark": true,
    "presentation": { "id": "...", "status": "ready" },
    "report_ready": true, "links": { "report": "/report/...", "presentation": "/presentation/..." } }
  ```

### Group F — Jobs / LinkedIn (Sai) `[STRETCH]`
- **`POST /jobs/search`** — `{ "session_id" | "profile", "target" }` → `{ "job_search_id", "status": "pending" }`.
- **`GET /jobs/{job_search_id}`** → `{ "status", "jobs": [ /* Job, §3 */ ] }`.
- **`POST /jobs/apply`** `[STRETCH]` — `{ "job_id", "document_id" }` → approval-gated auto-apply.
- Backed by: **Sai** (GUI agent drives LinkedIn/job boards in a remote desktop; see §5 + open question).

### Group G — Ops
- **`GET /health`** → `{ "status": "ok", "agents": { "resource": "up|down", "benchmark": "up|down" }, "redis": "up|down" }`.
  Lets us confirm the 2 uAgents registered before a demo.

---

## 3. Shared data objects
```jsonc
Profile  = { "skills": ["..."], "quantified_count": 0, "years_experience": 0.0,
             "education_level": "bachelor", "clarity_signal": 0.0, "summary": "..." }
Target   = { "kind": "job|school", "title": "...", "organization": "...",
             "required_skills": ["..."], "nice_to_have": ["..."] }
Category = { "score": 0, "weight": 0.0, "contribution": 0.0 }   // matches scoring.py to_payload()
Gap      = { "category": "quantified_achievements", "severity": "high|med|low",
             "current": 0, "target": 0, "why": "..." }
Lesson   = { "gap_category": "...", "title": "Quantified Impact",
             "principle": "...", "example": "...", "next_step": "...", "resources": [ Resource ] }
Resource = { "label": "...", "provider": "...", "url": "...", "cost": "free", "type": "course|cert|..." }
Slide    = { "index": 0, "title": "...", "body": "...", "speaker_notes": "...",
             "audio_url": "...", "bg_clip_url": "..." }
Job      = { "title": "...", "company": "...", "location": "...", "url": "...", "match_score": 0 }
```

---

## 4. End-to-end data flow (your rundown, mapped to endpoints + sponsors)

```
①  Chat / pitch (typed or spoken) + dream school/job
        │  spoken? POST /transcribe (Deepgram STT) → text
        ▼
②  POST /score { resume, target }
        ├─ Claude: extract Profile (skills, quantified count, years, edu, clarity)
        ├─ Claude: parse Target → required_skills
        ├─ scoring.py: signals → deterministic score + categories       (MASTER.md §7)
        └─ Claude: 1–3 lessons for the biggest gaps
        →  { score, categories, lessons, gaps, session_id, document_id }
        ▼
③  Enrich (parallel, off the same session_id):
        ├─ POST /benchmark  → Fetch.ai benchmark_agent → percentile + comparison
        ├─ POST /resources  → Fetch.ai resource_agent  → free resources per gap
        └─ POST /jobs/search → Sai → live postings / LinkedIn            [STRETCH]
        ▼
④  POST /presentation { session_id }   (async job)
        Claude (slide copy) → Deepgram (TTS per slide) → Pika (visuals) → narrated deck
        ▼
⑤  Summary / report page (3rd page):
        GET /sessions/{id} (what's ready) → GET /report/{id} (everything surfaced)
        score · per-category bars · percentile · skill comparison · gaps · lessons ·
        resources · roadmap (stages 1–4) · next steps · narrated slides
        ▼
⑥  Re-score loop: edit a bullet → POST /score { document_id, resume } → new version,
        returns previous_score → frontend animates old → new.   ← demo money shot
```
**Surfacing principle:** every backend output is addressable by an id and fetched with a `GET`. Adding a
new output later = add a producer + a `GET /{thing}/{id}` and list it in `GET /sessions/{id}`.

---

## 5. How each sponsor surfaces & uses the data

| Sponsor | Consumes | Produces | Endpoints | Role in score / next-steps / slides / summary |
|---------|----------|----------|-----------|-----------------------------------------------|
| **Claude** | resume/chat text, target text, gaps, benchmark | Profile, parsed Target, Gaps, **Lessons**, slide copy + speaker notes, `summary_text` | `/score`, `/presentation`, `/report` | Extraction + parsing **feed** the score (signals only — never the number); writes the lessons, the slide narrative, and the report prose |
| **Fetch.ai (uAgents)** | `gap_category`+context; `score`+target | curated **resources**; **percentile** + comparison | `/resources`, `/benchmark` | `resource_agent` = the next-steps content per gap; `benchmark_agent` = the "how do you stack up" percentile + which skills the top tier has |
| **Sai (Simular)** | profile, target | live **job postings**, LinkedIn data, real cohort profiles | `/jobs/search`, `/jobs/apply` | Live job data for next steps; enriches the benchmark cohort with real people; stretch: applies for the user (approval-gated) |
| **Deepgram** | audio in; lesson/slide text out | transcript; **mp3 narration** + `audio_url` | `/transcribe`, `/narrate` | Voice input on-ramp to `/score`; narrates the slides for the report/presentation page |
| **Redis** | every expensive result; job records | cache hits; job status | (all, internally) | Caches Claude/agent results by input hash; backs async jobs (presentation, jobs) and the session/document store |
| **Pika** | slide topics | background visuals / loops | `/presentation` (internal) | Visual layer behind the narrated slides (pre-generated, decoration over the core loop) |

---

## 6. Async & caching (Redis)
- **Cache:** `sha256(input)` → JSON result with TTL, for `/score`, `/benchmark`, `/resources`,
  `/transcribe` (near-idempotent). Cuts cost and makes re-scores feel instant.
- **Jobs:** `/presentation` and `/jobs/search` write a `{ id, status, result }` record; the frontend polls
  the matching `GET`. Keep it dead simple — Redis keys, no Celery.
- **Demo safety (MASTER.md Phase 5):** seed cohort + a couple of canned sessions so a live demo never
  blocks on a cold/slow agent. `/health` confirms the uAgents are up first.

---

## 7. Contract alignment vs FRONTEND.md
| FRONTEND.md | Status here | Notes |
|-------------|-------------|-------|
| `POST /score {resume,target} → {score,categories,lessons}` | **kept verbatim** + additive ids/gaps | re-callable; `previous_score` powers old-vs-new |
| `POST /benchmark {score,target} → {percentile}` | **kept verbatim** + `comparison` `[ADD]` | percentile unchanged |
| `POST /resources {gap_category,context} → {resources}` | **kept verbatim**; item shape TBD | confirm `str` vs object on hour 1 |
| Narrated Lesson Player (slides + TTS audio) | `/presentation` + `/narrate` | matches FRONTEND.md stretch #5 |
| Deepgram → audio URL played via `<audio>` | `/narrate` returns `audio_url` | exact match |
| Fetch.ai called via backend only | `/resources`, `/benchmark` | frontend stays sponsor-agnostic |

**The only field that needs an explicit frontend decision is the `/resources` item shape** (string vs object).
Everything else is either locked or additive (safe to ignore on the frontend until wired).

---

## 8. Phasing & open questions
**MVP (core loop):** `/score`, `/benchmark`, `/resources`, `/transcribe`, `/narrate`, `/health`;
session+document state in Redis. Get score → lesson → benchmark working end-to-end first (FRONTEND.md objective).
**Next:** `/documents` versioning, `/presentation`, `/report` + `/sessions`.
**Stretch:** `/jobs/*` (Sai), persistent Postgres store, `/jobs/apply`.

**Open:**
- **Sai handoff** — public API vs a side workflow that exports data we ingest? Auto-apply in scope? (MASTER.md §12)
- **`/resources` item shape** — `str` vs object — lock with frontend hour 1.
- **Document persistence** — Redis-TTL only for the hackathon, or Postgres if we want real history?
- **Benchmark cohort** — seeded demo profiles only, or live-enriched via Sai/LinkedIn?
