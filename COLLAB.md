# COLLAB.md — running the backend for the team

The question everyone asks: *"do my teammates need my API key?"* **No.**

## The one rule

**The Anthropic key lives ONLY on the backend. The browser never sees it.**

```
  Teammate's browser (frontend)                 YOUR backend                 Anthropic
  ────────────────────────────                  ───────────                  ─────────
  fetch(BACKEND_URL + "/score")  ───HTTP──▶  FastAPI (.env has the key) ──▶  Claude
                                 ◀──JSON───  parses + scores                 returns
  renders the result
```

The frontend only ever sends the resume/target and receives JSON. The key stays
server-side. So teammates need **the backend's URL**, never the key or your `.env`.

## Two different `.env` files (this is the confusion)

| File | Where | Contains | Shared? |
|------|-------|----------|---------|
| `backend/.env` | backend project | `ANTHROPIC_API_KEY=...` (the secret) | **NEVER** — gitignored |
| `frontend/.env` | frontend project | `VITE_API_BASE_URL=<your backend URL>` (just a URL, no secret) | fine to share the URL |

So: **you** run the backend with the key; **you give your teammates the backend URL**;
they put it in their frontend `.env` as `VITE_API_BASE_URL`. That's the whole handshake.

## Making it work on ALL computers

`http://localhost:8000` only works on **your** machine — `localhost` means "this
computer." To let teammates on other machines hit your always-on backend (with Claude
enabled), pick one:

### Option A — Tunnel (recommended for the hackathon, ~30 seconds)
Run your backend, then expose it with a public URL. No deploy, key stays on your laptop.

```bash
# terminal 1 — the backend (with your key in backend/.env)
cd backend && uvicorn app.main:app --reload --port 8000

# terminal 2 — a public tunnel to it (no signup):
brew install cloudflared          # one-time
cloudflared tunnel --url http://localhost:8000
#  -> prints a URL like https://random-words.trycloudflare.com
```

Give that `https://….trycloudflare.com` URL to the frontend team → they set
`VITE_API_BASE_URL=https://….trycloudflare.com`. Done — their frontend now uses your
backend + your Claude key, from any computer. (ngrok works too: `ngrok http 8000`.)

> If you use voice (`/narrate`): also set `PUBLIC_BASE_URL=<tunnel URL>` in `backend/.env`
> so the audio links resolve. Not needed just to test the first page (score/report).

### Option B — Each teammate runs their own backend
`git clone`, `pip install -r backend/requirements.txt`, `uvicorn app.main:app`.
- With **no key** → it still works (free heuristic extractor) — great for frontend dev.
- With Claude parsing → each person needs their **own** key in their **own** `backend/.env`
  (or you share the key *value* out-of-band via 1Password/DM — never via git).

### Option C — Deploy it (Render / Railway / Fly)
Push the backend, set `ANTHROPIC_API_KEY` as a host env var, share the deployed URL.
More setup; do this only if you want a permanent URL.

## CORS — already handled

CORS is about *where the frontend is served from*, not which machine. Every teammate
running the frontend at `http://localhost:5173` (or any local port) is **already
allowed** — the backend permits any `localhost`/`127.0.0.1` origin out of the box. If
someone serves the frontend from a **deployed** URL, add it to `CORS_ORIGINS` in
`backend/.env` (comma-separated), e.g.
`CORS_ORIGINS=https://hired.vercel.app`.

## "Keep the key always enabled so we can double-check the first page"

Run **Option A** and leave both terminals up. The frontend team points
`VITE_API_BASE_URL` at your tunnel URL and tests the real flow (Claude parsing
included). The key never leaves your laptop. When you stop the tunnel, the URL dies —
restart it and re-share the new URL (or use `cloudflared`'s named tunnels / ngrok for
a stable URL).

## TL;DR
1. You run the backend (key in `backend/.env`) + a tunnel.
2. You send the team the tunnel URL.
3. They put it in their frontend `.env` as `VITE_API_BASE_URL`.
4. Teammates never need the key. The app also runs free (no key) for frontend dev.

---

## Frontend integration — paste THIS to the frontend team

They need one thing from you: the backend URL (your tunnel link) as `VITE_API_BASE_URL`.
No key. Then call these. **Everything is JSON except `/score`, which is multipart.**

`POST {VITE_API_BASE_URL}/score` — **multipart/form-data** (NOT JSON):
- `user_id` — a UUID generated once per visitor (`crypto.randomUUID()`)
- `target` — a JSON **string**: `JSON.stringify({ type: "role", value: "<dream job/school>" })`
- `resume_file` — the uploaded `.pdf`/`.docx`/`.rtf`/`.txt`  **OR**  `resume_text` — pasted text

```js
const fd = new FormData();
fd.append("user_id", crypto.randomUUID());
fd.append("target", JSON.stringify({ type: "role", value: targetText }));
if (file) fd.append("resume_file", file); else fd.append("resume_text", text);
const r = await fetch(`${import.meta.env.VITE_API_BASE_URL}/score`, { method: "POST", body: fd });
const data = await r.json();
// data = { score, categories, lessons, matched_skills, missing_skills, status }
```

The rest are plain `POST` with a JSON body:
- `/benchmark` → `{ user_id, score, target:{type,value} }` → `{ percentile, sample_size, message }`
- `/resources` → `{ user_id, gap_category, context:{first_gen,target_type} }` → `{ resources:[{name,url,description}] }`
- `/report` → `{ user_id, target, score, categories, lessons, matched_skills, missing_skills, percentile }` → `{ summary, strengths, weaknesses, next_steps, jobs, mentors, slides }`
- `/narrate` → `{ text }` → `{ audio_url }` (play in an `<audio>` tag)

Full request/response shapes: **`API_CONTRACT.md`**. No API key ever goes in the frontend.
