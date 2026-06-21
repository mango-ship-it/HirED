# HirED API — Endpoint Reference (for the frontend)

**Base URL:** the cloudflared tunnel (ask Kaden for the current `https://<…>.trycloudflare.com`).
**Keys:** all API keys live on the backend — never call Claude/Exa/Deepgram/fal from the browser.
**user_id:** generate a UUID once and keep it in `localStorage`; send the **same** one to every call so the user's data persists.

```js
function getUserId(){let id=localStorage.getItem('hired_user_id');if(!id){id=crypto.randomUUID();localStorage.setItem('hired_user_id',id);}return id;}
```

All responses are JSON. `/score` and `/transcribe` take multipart; everything else takes JSON.

---

## Results-page flow

### 1 · `POST /score`  — the readiness score (pages 1–3)
Multipart form:
| field | value |
|---|---|
| `user_id` | the localStorage UUID |
| `target` | JSON string `{"type":"role","value":"Bus Driver"}` |
| `resume_file` **or** `resume_text` | the `.pdf`/`.docx` file, or pasted text |

```jsonc
{
  "score": 84,                         // 0–100
  "categories": {                      // page 2: bars + explanation
    "skills_match":            { "score": 70, "weight": 0.35, "explanation": "You show 2 of ~5 skills…" },
    "quantified_achievements": { "score": 100, "weight": 0.25, "explanation": "…" },
    "experience":              { "score": 100, "weight": 0.20, "explanation": "…" },
    "education":               { "score": 50, "weight": 0.10, "explanation": "Detected education: some college." },
    "clarity":                 { "score": 92, "weight": 0.10, "explanation": "…" }
  },
  "lessons": [                         // pages 3–5: the gaps (1–3)
    { "category": "education", "principle": "…", "example": "…", "action": "…" }
  ],
  "matched_skills": ["…"],
  "missing_skills": ["…"],
  "status": { "scoring": "complete", "benchmark": "pending", "resources": "pending" }
}
```
> Same input always returns the same score (deterministic + cached).

### `POST /resources`  — "free ways to close this gap" (pages 3–5)
Body: `{ "gap_category": "education", "context": "Bus Driver", "user_id": "…" }`  — `context` is the **role string**; `gap_category` is one of the 5 category keys. **Send `user_id`** so each `description` is personalized to the user's own resume gaps (e.g. a CNA targeting RN gets why-it-helps about fast-track RN training), not a generic role blurb.
```jsonc
{ "resources": [ { "name": "PGA Coach", "url": "https://…", "description": "One-sentence what-it-is + why it helps." } ] }
```

### `POST /benchmark`  — "how you compare" (page 6)
Body: `{ "user_id": "…", "score": 84, "target": { "type":"role", "value":"Bus Driver" } }`
```jsonc
{
  "percentile": 79,
  "sample_size": 4,
  "message": "You're ahead of 79% of candidates…",
  "transparency": "Your readiness score (84/100)… each candidate is scored 0–100 the same way…",  // page-6 explanation
  "candidates": [                      // real LinkedIn profiles, each SCORED 0–100 (deterministic)
    { "name": "Jane Doe", "url": "https://linkedin.com/in/…", "score": 88, "why_stronger": "32+ years leading…" }
  ],                                   // plot each on a red→yellow→green scale; score < user = behind, > user = ahead
  "matches": []                        // populated only if the Fetch.ai 2AFC agent is running
}
```

### `POST /roadmap`  — "your roadmap" (page 7, unlock-as-you-go)
Body: `{ "target":"Bus Driver", "location":"Oakland, CA", "skills":["CDL"], "user_id":"…" }` (skills optional — falls back to the user's stored missing_skills).
```jsonc
{
  "exa": true, "role": "Bus Driver",
  "steps": [                           // render this; flip `locked` as the user finishes each
    { "order":1, "id":"skill-cdl-1", "kind":"skill", "title":"Learn CDL", "locked":false,
      "resources": [ { "name":"…", "url":"…", "type":"course", "why":"…", "description":"…" } ] },
    { "order":2, "id":"certifications-2", "kind":"certifications", "title":"Earn a certification", "locked":true, "resources":[…] }
    // kinds: skill · certifications · events · people · networking · scholarships
  ],
  "events":[…], "networking":[…], "people":[…], "certifications":[…], "scholarships":[…]   // raw lists too
}
```

### `POST /learning-plan`  — per-skill resources (alt to /roadmap)
Body: `{ "target":"Bus Driver", "location":"…", "skills":["CDL"], "user_id":"…", "company":"…" }`
```jsonc
{
  "role":"…", "location":"…", "is_coding":false,
  "items": [ { "skill":"CDL", "resources":[ {name,url,type,why,description} ], "credential_note":"…" } ],
  "role_resources": [ {name,url,type,why,description} ],
  "company_practice": { "company":"google", "problems":[ {id,title,url,difficulty,acceptance,frequency,description} ] }  // coding roles only
}
```

---

## Voice + video (the tab below the roadmap)

### `POST /narrate`  — text-to-speech
Body `{ "text":"…" }` → `{ "audio_url": "/static/audio/…mp3" }` — **relative**, so play `API_BASE + audio_url`.

### `POST /intelligence`  — topics/sentiment for visuals
Body `{ "text":"…" }` or `{ "user_id":"…" }` → `{ "summary":"…", "topics":[…], "intents":[…], "sentiment":{label,score}, "configured":true }`.

### `POST /voice-agent/config`  — conversational voice agent
Body `{ "user_id":"…" }` →
```jsonc
{ "configured": true, "ws_url": "wss://agent.deepgram.com/v1/agent/converse",
  "token": "…",            // short-lived; open the Deepgram Voice Agent WS with this
  "greeting": "Hi! I see you're aiming for Bus Driver…",
  "settings": { … } }       // send verbatim to Deepgram; system prompt already has the user's data
```

### `POST /video`  — Pika "your journey" video (async)
Body `{ "user_id":"…" }` (or `{role}`/`{prompt}`) → `{ "prompt_hash":"…", "status":"generating" }`.
Then poll **`GET /video/{prompt_hash}`** → `{ "status":"ready", "video_url":"https://…" }` and play it.

---

## Supporting

| Method · Path | Body / params | Returns |
|---|---|---|
| `GET /health` | — | `{status, store, vector_index, claude_configured, deepgram_configured, exa_configured, fal_configured}` |
| `GET /profile/{user_id}` | — | the saved profile (404 if unseen) |
| `POST /progress` | `{user_id, progress:{…}}` | `{user_id, saved:true}` — persists roadmap progress |
| `GET /progress/{user_id}` | — | `{user_id, progress:{…}}` |
| `POST /jobs/refresh` | `{target, location?}` | pulls real postings (slow, 10–30s) → caches them |
| `GET /jobs/{target}/skills?user_id=` | — | `{sample_size, market_skills:[{skill,count}], you_have, you_lack}` |
| `GET /leetcode/{company}?period=&limit=` | — | `{count, problems:[{id,title,url,difficulty,acceptance,frequency,description}]}` |
| `POST /transcribe` | multipart `audio` | `{text}` |
| `POST /report` | `{user_id, score, target, …}` | `{summary, strengths, weaknesses, next_steps, jobs, mentors, slides}` |

---

## Patterns to know
- **Every resource card** is `{ name, url, type, why, description }` (roadmap + learning-plan) or `{ name, url, description }` (/resources). Render `name` as the link, `description` as the one-line why.
- **Graceful states:** voice/video/intelligence can return `{"configured": false, …}` (key not set) or `{"status":"error"}` — just hide that piece.
- **Errors:** validation issues return `{"error":"…","code":"INVALID_INPUT"}` with a 4xx.
