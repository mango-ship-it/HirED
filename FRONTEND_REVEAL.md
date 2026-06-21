# Frontend Reveal Guide — new backend capabilities

How to surface everything the backend now does, on the results page. All endpoints are
live on the `backend` branch. Base URL = the cloudflared tunnel (ask Kaden for the
current `https://<...>.trycloudflare.com`). No API keys in the frontend — they live on
the backend only.

---

## 0. The `user_id` (do this once)
Generate a UUID **once** and persist it in `localStorage` so per-user memory works across
sessions. Do **not** regenerate per page load.

```js
function getUserId() {
  let id = localStorage.getItem('hired_user_id');
  if (!id) { id = crypto.randomUUID(); localStorage.setItem('hired_user_id', id); }
  return id;
}
```

Send this `user_id` to every endpoint. What's per-user: the profile/score/skills. What's
shared (not per-user): the jobs cache (by role) and the resource vector index.

---

## 1. `POST /score` — the first page (unchanged contract, now smarter)
Multipart form. Same shape as before, BUT: if you call `POST /jobs/refresh` for the same
target **first** (see §2), `matched_skills` / `missing_skills` reflect **real market
demand**, not a guess.

```js
const fd = new FormData();
fd.append('user_id', getUserId());
fd.append('target', JSON.stringify({ type: 'role', value: 'Data Analyst' }));
fd.append('resume_text', pastedText);           // OR fd.append('resume_file', file);
const res = await fetch(`${BASE}/score`, { method: 'POST', body: fd }).then(r => r.json());
// { score, categories:{skills_match:{score,weight},...}, lessons:[{category,principle,example,action}],
//   matched_skills:[...], missing_skills:[...], status:{scoring,benchmark,resources} }
```
> The target `value` in `/score` must match the `/jobs/refresh` target string (same Redis key).

---

## 2. `POST /jobs/refresh` — prefetch real postings (demo prep / on target select)
Slow (10–30s, scrapes real boards). Call it when the user picks a target, with a loading
state — or prefetch your demo roles ahead of time. Caches to Redis so later reads are instant.

```js
await fetch(`${BASE}/jobs/refresh`, {
  method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ target: 'Data Analyst', location: 'Oakland, CA' }),
});
// { target, count, stored, jobs:[{title,company,location,url,site,description}] }
```

---

## 3. `GET /jobs/{target}/skills?user_id=` — "real market demand" panel
What employers actually ask for (ranked by # of postings), and the user's have/lack.

```js
const m = await fetch(`${BASE}/jobs/${encodeURIComponent('Data Analyst')}/skills?user_id=${getUserId()}`)
  .then(r => r.json());
// { sample_size, market_skills:[{skill,count}], you_have:[...], you_lack:[...] }
```
UI: a bar/chip list — "9/12 postings want **SQL** ✓ you have it · 7/12 want **Tableau** ✗ gap".
If `sample_size === 0`, there's no cached jobs yet (call §2 first).

---

## 4. `POST /learning-plan` — the roadmap + real resources (the money screen)
Domain-agnostic. Works for chef, bus driver, social worker, software. Pass `skills`
(the gaps), or a `user_id` (uses their stored `missing_skills`), or just a `target`.

```js
const plan = await fetch(`${BASE}/learning-plan`, {
  method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    target: 'Social Worker', location: 'Oakland, CA',
    skills: ['Case Management','Crisis Intervention','Trauma-Informed Care'],
    // optionally: user_id, company (for coding roles)
  }),
}).then(r => r.json());
```
Response:
```jsonc
{
  "role": "Social Worker", "location": "Oakland, CA", "is_coding": false,
  "items": [
    { "skill": "Case Management",
      "resources": [
        { "title": "...", "type": "video",  "url": "https://youtube.com/results?...", "why": "..." },
        { "title": "...", "type": "course", "url": "https://coursera.org/search?...",  "why": "..." },
        { "title": "...", "type": "local",  "url": "https://google.com/search?...near...", "why": "...", "near_you": true }
      ],
      "credential_note": "Heads-up: some programs ask for a diploma/GED or prerequisite..." }
    // ...one per gap = the roadmap steps, in order
  ],
  "role_resources": [
    { "title": "Social Worker: certifications & licenses needed", "type": "credential", "url": "..." },
    { "title": "Social Worker schools/programs near Oakland, CA",  "type": "local", "url": "...", "near_you": true }
  ],
  // ONLY present for a coding role at a known company:
  "company_practice": { "company": "google", "note": "...",
    "problems": [{ "id","title","url","difficulty","acceptance","frequency" }] }
}
```
UI: render `items` as a numbered **roadmap** (step 1, 2, 3…); each step is a card with its
resource buttons grouped by `type` (🎥 video / 🎓 course / 📍 local / 🧩 practice). Show
`role_resources` as a "credentials & local programs" footer. If `company_practice` exists,
show a "Practice these at {company}" list (problems are frequency-ranked — top = most asked).

---

## 5. `GET /leetcode/{company}` — company interview problems (coding only)
Standalone, if you want a dedicated panel. `period` = thirty-days | three-months | six-months | all.

```js
const lc = await fetch(`${BASE}/leetcode/google?period=thirty-days&limit=15`).then(r => r.json());
// { company, period, count, problems:[{id,title,url,difficulty,acceptance,frequency}] }
```

---

## 6. Already available (existing)
- `GET /resources` — semantic free resources (RedisVL vector search) for a gap category.
- `GET /profile/{user_id}` — recall a returning user's stored profile (404 if unseen).
- `POST /report` — the templated report/slides.
- `POST /benchmark` — percentile (Inseon's 2AFC/ELO pipeline lands here).

---

## Recommended reveal order on the results page
1. **Score + category radar** (`/score`)
2. **Real market demand** — have/lack chips (`/jobs/{target}/skills`)
3. **Roadmap + resources** — the numbered learning plan (`/learning-plan`)
4. **Lessons** (from `/score`) and, for coding, **company practice** (inside the plan)
5. **Benchmark percentile** when ready (`/benchmark`)

## Health check
`GET /health` → confirm `"store":"redis"` and `"vector_index":"ready"` before demoing.
