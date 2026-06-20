# FRONTEND.md

## Stack
- React + Vite + Tailwind v4 + React Router
- State: `useState`/Context — no Redux needed at this scope, don't add it

## Core Screens (MVP — build and test these first, in this order)
1. **Upload Screen** — resume upload (drag-drop, PDF/docx) + target input (typed job/school, or a textarea to paste a real job posting's text)
2. **Loading State** — AI calls take 5–15s. Always show a skeleton/spinner. A blank screen during a live demo reads as "broken," not "thinking."
3. **Results Screen** — score number, per-category breakdown bars, 1–3 lesson cards, peer percentile
4. **Re-score Flow** — edit a bullet → re-score → show old vs. new score side by side. **This is the demo's money shot — test it explicitly and early, don't discover it's broken at hour 20.**

## Stretch Goals (only after MVP above is built AND tested end-to-end)
5. **Narrated Lesson Player** — animated slide cards + TTS audio, auto-advance on the audio's `onEnded` event
6. **Resource Card** — renders the Fetch.ai agent's curated resource list as the final card/slide

## API Contract (lock this with backend on hour 1 — mismatched shapes are the #1 cause of late-night merge pain)
- `POST /score` — `{ resume, target }` → `{ score, categories: {...}, lessons: [...] }`
- `POST /benchmark` — `{ score, target }` → `{ percentile }` (Fetch.ai agent, called via backend)
- `POST /resources` — `{ gap_category, context }` → `{ resources: [...] }` (Fetch.ai agent, called via backend)

Build against a mocked version of these shapes before the real endpoints exist — don't block frontend work waiting on backend.

## Sponsor Tools — What Actually Touches the Frontend
- **Anthropic (Claude)** — never called directly from the frontend. Routed through the backend so the API key stays server-side. Frontend just hits `/score`.
- **Deepgram** — backend returns an audio URL; frontend just plays it via a standard `<audio>` tag.
- **Pika** — pre-generated background clips only (not live-generated). Rendered as a muted `<video loop autoPlay>` behind lesson text.
- **Fetch.ai** — frontend never talks to the agent directly; it calls your backend, which messages the agent. Frontend just renders whatever JSON comes back.

**Honest note on "could this have come from the sponsors":** most sponsor starter packs (Anthropic's build-with-Claude guide, Fetch.ai's uAgent quickstart) are API/SDK docs for the *backend* side of an integration — none of them ship a frontend architecture template for a project like this. This file is us defining that structure ourselves, not something pulled from a sponsor resource.

## Educational Design Principles (bake into the UI itself, not just the copy)
- Label every score as a **skill**, not a bare number — "Quantified Impact: 40/100," never just "40"
- Every low-scoring category ships with a **micro-lesson**: principle → example → one concrete next step
- Peer comparison is framed as **guidance**, never a leaderboard — "users who moved from your range up fixed X first," not just a percentile alone
- Show a **per-category breakdown**, not one aggregate number — this is what makes it feel like a learning tool, not a grade

## Common Mistakes to Avoid
- ⚠️ Building UI before the API contract is agreed with backend — use a mock/stub, swap in the real call once both sides confirm the shape
- ⚠️ Skipping loading states — AI scoring isn't instant; silence looks like a crash
- ⚠️ Letting video/narration work block the core score → lesson → benchmark loop — that loop is the MVP, video is decoration
- ⚠️ Leaving the re-score demo flow untested until the night before — verify it works with real data, not just placeholder text
- ⚠️ Hardcoded demo data that never gets swapped for the real API call before presenting
- ⚠️ Scope creep — if a feature isn't in the MVP list above, it's optional. Check this file before starting something new.

## Objective
Get the score → lesson → benchmark loop fully working end-to-end before touching anything else. Everything past that — video, Pika, polish — is bonus, and only happens if the core loop is demo-ready first.
