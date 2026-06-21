# Exa Integration Contract (for Inseon's JD + search work)

Two places your Exa data plugs into the backend. If you match these shapes, **everything
downstream works with zero changes** — the accuracy wire, the grounded lessons, the
market-skills panel, and the learning-plan resources all already consume these.

---

## 1. Job descriptions → the `jobs` shape (powers scoring + lessons + market panel)

Whatever Exa returns for a target role, normalize each posting to this dict and store the
list in Redis under the **same key our pipeline reads** (`jobs:{target}`):

```python
job = {
  "title":       str,   # required
  "company":     str,
  "location":    str,
  "url":         str,
  "site":        str,   # "exa" is fine
  "description": str,   # the JD text — richer is better (this is what grounds lessons)
}
```

Store it the easy way (reuses our store + key):
```python
from app.services.store import get_store
from app.services.jobs import jobs_key
await get_store().set_json(jobs_key(target), jobs, ttl=604800)   # target e.g. "Data Analyst"
```

Once that's in Redis, with **no other changes**:
- `POST /score` (same target string) measures skills against real demand,
- the lessons cite real requirement excerpts (grounded, anti-hallucination),
- `GET /jobs/{target}/skills` shows the have/lack panel.

> Exa can replace or augment JobSpy here — they produce the same shape. Cleaner/fuller
> `description` text = better grounding. The target string in `/score` must match the key.

---

## 2. Real resources → `resources_by_skill` (upgrades the roadmap from search-links to real URLs)

Today `/learning-plan` returns **search links** (`youtube.com/results?...`). Exa lets us
return the **actual best video/course/article per skill**. Produce a map of skill → ranked
resource cards:

```python
resources_by_skill = {
  "Case Management": [
    {"title": "...", "url": "https://...", "type": "video",   "why": "..."},
    {"title": "...", "url": "https://...", "type": "course",  "why": "..."},
    {"title": "...", "url": "https://...", "type": "article", "why": "..."},
  ],
  "Crisis Intervention": [ ... ],
}
```
- `type` ∈ video | course | article | local | practice (drives the UI icon).
- Use Exa search (+ contents) to find real, current, free-leaning resources per skill.

Then the plan builder uses them automatically (falls back to search-links for any skill
you don't cover):
```python
from app.services.learning_plan import build_plan
plan = build_plan(skills, role=target, location=loc, resources_by_skill=resources_by_skill)
```

I'll wire an Exa adapter into the `/learning-plan` route that calls your function and
passes `resources_by_skill` through — so the moment your search returns this shape, the
roadmap shows real resources. **The seam already exists; nothing on my side blocks you.**

---

## TL;DR
- JDs → `jobs` shape under `jobs:{target}` → scoring/lessons/market panel light up.
- Resources → `{skill: [{title,url,type,why}]}` → `build_plan(resources_by_skill=...)` →
  real roadmap resources instead of search links.
- Keep `description` text rich (grounding) and resource lists short + ranked (top 3-4/skill).
