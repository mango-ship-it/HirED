# API_CONTRACT.md

Locked together by frontend + backend — update this file the moment anything changes. This is the single source of truth, not FRONTEND.md's rough sketch.

---

## 1. `POST /score`

**DECIDED:** Frontend sends the raw file (multipart `FormData`); backend parses it (`pdfplumber`/`python-docx`) and feeds extracted data to the agents. Frontend does no PDF parsing.

**Request:** (multipart form data, not raw JSON — file upload)

```
user_id: "string — UUID generated client-side on first visit"
resume_file: <binary file, .pdf or .docx>
target: {
  "type": "role" | "school" | "job_posting_text",
  "value": "string — e.g. 'Software Engineering Internship' or pasted job posting text"
}
```

**Response (200):**

```json
{
  "score": 72,
  "categories": {
    "skills_match":            { "score": 65, "weight": 0.35 },
    "quantified_achievements": { "score": 40, "weight": 0.25 },
    "experience":              { "score": 80, "weight": 0.20 },
    "education":               { "score": 90, "weight": 0.10 },
    "clarity":                 { "score": 70, "weight": 0.10 }
  },
  "lessons": [
    {
      "category": "quantified_achievements",
      "principle": "Recruiters scan for numbers — unquantified bullets get skipped.",
      "example": "Before: 'Helped improve process' → After: 'Reduced processing time 30%'",
      "action": "Add a number to bullet 2 of your projects section."
    }
  ],
  "matched_skills": ["python", "sql"],
  "missing_skills": ["airflow", "dbt"],
  "status": {
    "scoring": "complete",
    "benchmark": "complete" | "pending" | "failed",
    "resources": "complete" | "pending" | "failed"
  }
}
```

**`matched_skills` / `missing_skills`** _(additive — added by backend, frontend please confirm)_: the target skills the candidate already has vs. lacks. `missing_skills` is the data source for the **"what the top tier has that you don't"** chips on the readiness/benchmark view (the landing page currently hardcodes these).

**Why `status` exists:** scoring now pulls data from multiple agents (Fetch.ai + scoring agent) running in parallel. Per decision on #6, a slow/failed agent does NOT fail the whole request — `/score` still returns what it has. Frontend reads `status` and conditionally renders the benchmark/resources sections instead of assuming they're always present. If `"pending"`, frontend can poll or just show a "still calculating" state for that section; if `"failed"`, hide that section gracefully rather than showing broken/empty data.

---

## 2. `POST /benchmark`

**Frontend story (one sentence):** the FE shows a "how prepared are you?" view with a percentile gauge and a head-to-head reveal of the synthetic candidates the user beat or lost to.

**Request:**

```json
{
  "user_id": "string — same UUID sent with /score",
  "score": 72,
  "target": { "type": "role", "value": "Software Engineering Internship" }
}
```

**Response (200):**

```json
{
  "percentile": 65,
  "sample_size": 8,
  "message": "You're ahead of 65% of candidates targeting Software Engineering Internship. Candidates who broke into the top tier most often strengthened their lowest-scoring category first — that's the fastest way to move your number.",
  "matches": [
    {
      "competitor_headline": "Alex Chen | Software Engineering Intern",
      "competitor_resume": "Alex Chen | Software Engineering Intern\nEducation: BS CS, MIT, GPA 3.95 (2024)\nExperience:\n  - SWE Intern @ Stripe (Summer 2023, 3 mo)\n    * Built real-time fraud detection feature; blocked $2.1M/mo in fraud\n...",
      "user_won": false
    },
    {
      "competitor_headline": "Jamie Wilson | Career Changer",
      "competitor_resume": "Jamie Wilson | Career Changer\nEducation: BA English Literature, State University (2020)\nExperience:\n  - Barista @ Local Coffee Shop (2020–2023, 3 yr)\n...",
      "user_won": true
    }
  ]
}
```

**Field notes:**

- `sample_size` is the number of synthetic competitors the user was compared against this request (the 2AFC cohort: typically 5–8 synthesized + tier-stratified, or 30 on agent fallback). It is **not** a historical user count.
- `matches[]` carries one entry per 2AFC comparison: the competitor headline (first line of the synthesized resume), the full synthesized resume text, and whether the user won the head-to-head. **Synthesized competitors are LLM-generated** — the FE must label them as such (e.g. "AI-generated peer profile") rather than implying they are real people.
- On agent-unavailable fallback the field is always present but empty (`"matches": []`).
- `message` is a plain-language framing of `percentile` produced server-side; the exact copy may evolve — treat it as opaque display text.

---

## 3. `POST /resources`

**Request:**

```json
{
  "user_id": "string — same UUID sent with /score",
  "gap_category": "quantified_achievements",
  "context": {
    "first_gen": true,
    "target_type": "tech_internship"
  }
}
```

**Response (200):**

```json
{
  "resources": [{ "name": "string", "url": "string", "description": "string" }]
}
```

---

## 4. `POST /report` _(additive — backend, frontend please confirm)_

The summary/report page (3rd page). Send the data the frontend already has from
`/score` (+ `/benchmark`, `/resources`); the backend assembles a narrative report +
a narratable slide deck and adds Sai-sourced jobs/mentors. **Templated — no API cost.**

**Request:**

```json
{
  "user_id": "string",
  "target": { "type": "role", "value": "Marketing Coordinator" },
  "score": 58,
  "categories": { "skills_match": { "score": 65, "weight": 0.35 }, "...": {} },
  "lessons": [
    { "category": "...", "principle": "...", "example": "...", "action": "..." }
  ],
  "matched_skills": ["..."],
  "missing_skills": ["..."],
  "percentile": 40,
  "resources": [{ "name": "...", "url": "...", "description": "..." }]
}
```

**Response (200):**

```json
{
  "summary": "string",
  "strengths": ["string"],
  "weaknesses": ["string"],
  "next_steps": ["string"],
  "jobs": [{ "title": "", "company": "", "location": "", "url": "" }],
  "mentors": [{ "name": "", "role": "", "company": "", "url": "", "why": "" }],
  "slides": [{ "index": 0, "title": "", "body": "", "speaker_notes": "" }]
}
```

`slides[].speaker_notes` is the narratable text — pass it to `POST /narrate` for TTS.
`jobs`/`mentors` come from Sai (pysimular) when wired, else a built-in demo seed.

---

## Error Shape (all endpoints, same format)

```json
{
  "error": "string — human-readable message",
  "code": "INVALID_INPUT" | "PARSE_FAILED" | "AGENT_TIMEOUT" | "SERVER_ERROR"
}
```

HTTP status: `400` for bad input, `500` for anything that breaks server-side. Fetch.ai agent timeouts do **not** return 504 — `/benchmark` and `/resources` fall back to a deterministic local result and still return 200 with the contract shape (e.g. `/benchmark` returns `matches: []` and a `percentile` derived from the score). Frontend should not write 504-handling for these endpoints.

---

## Other Things to Lock Down in the Same 10 Minutes

- [ ] **Naming convention:** use `snake_case` everywhere, including in the frontend JS objects. Don't build a camelCase → snake_case transformer — not worth the time in a hackathon, just match Python/Pydantic's default on both sides.
- [ ] **Base URL:** confirm the FastAPI dev port (e.g. `http://localhost:8000`) and put it in a `.env` var on the frontend (`VITE_API_BASE_URL`), not hardcoded.
- [ ] **CORS:** backend must explicitly allow the Vite dev server's origin (e.g. `http://localhost:5173`) via `CORSMiddleware` — confirm this is added before frontend starts testing real calls, it's a classic hour-3 blocker.
- [ ] **Timing expectations:** `/score` chains a Claude call — confirm rough latency (5–15s) so frontend's loading state duration assumption is realistic, not a guess.
- [ ] **Session/user identifier:** do we need any ID per submission for the Redis-based peer benchmark, or is each `/score` call stateless until the user explicitly opts into benchmarking? Decide now — affects whether frontend needs to generate/store anything.
- [ ] **File size/type limits:** confirm max resume upload size and accepted types (`.pdf`, `.docx`) so frontend can validate before sending, not after a failed request.

---

**Once this file changes from a live discussion, whoever changed it pings the other side immediately — don't let this drift out of sync with what's actually implemented.**
