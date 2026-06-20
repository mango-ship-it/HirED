---
name: plan-feature
description: Turn a feature idea, task, or project into a phased build plan with per-phase checkbox TODOs, owners, MVP-vs-stretch split, open questions, and risks. Use when the user asks to "plan", "break down", "scope", or wants "phases"/"todos" for something — especially under a deadline (hackathon, sprint).
---

# plan-feature — phased task planner

Produce a build plan someone can start executing immediately. Optimize for shipping a working
**thin end-to-end slice first**, then breadth, then polish.

## Steps

1. **Restate the goal in one line.** If the goal is unclear or has genuine forks (scope, data
   source, which input first), ask 2–4 crisp clarifying questions BEFORE writing the plan. Don't ask
   about things with an obvious default — pick the default and mark it `[ASSUMPTION]`.

2. **Capture constraints.** Deadline / time budget, team + who owns what, fixed stack, sponsor or
   tooling requirements. These shape everything below.

3. **Define the thin slice.** The smallest path that exercises the whole system end-to-end
   (input → process → visible output). This is Phase 1. Resist building breadth before the slice works.

4. **Break into phases.** Typical shape:
   - **Phase 0 — Setup** (scaffold, env/keys, contracts)
   - **Phase 1 — Thin end-to-end slice** (the spine works)
   - **Phase 2..N — Breadth** (one capability per phase)
   - **Final — Polish, demo/ship prep, seed/fallback data**

   Each phase = a short title + concrete **checkbox** TODOs (`- [ ]`). Tag owners when known
   (`*(Bobby)*`). Keep each TODO small enough to finish in one sitting.

5. **Split MVP vs stretch.** Mark must-haves vs nice-to-haves explicitly. Under a deadline, default
   to cutting breadth, not the thin slice.

6. **List open questions / decisions needed.** Anything you assumed, plus real forks for the user.

7. **Flag risks.** External dependencies (APIs that may be slow/async, scraping, auth) and the single
   thing most likely to break the demo — each with a fallback.

## Output format
Markdown with: a one-line goal, a constraints line, numbered phases with checkbox TODOs, an
MVP-vs-stretch split, and an open-questions list. If the project has a `MASTER.md` (or similar source
of truth), update it there instead of dumping a throwaway plan. Keep it skimmable — tables and
checklists over prose.

## Principles
- **Thin slice before breadth.** A working spine beats three half-built features.
- **Every TODO is a verb + a concrete artifact.** "Wire `getReport` to return score" — not "do backend".
- **Name the demo money-shot early** and protect time for it.
- **Prefer seeded/fallback data** so a live demo never depends on a cold or flaky API.
