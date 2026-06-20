"""Fetch live LinkedIn jobs + mentors via Sai (pysimular) -> write the JSON the
backend ingests (`app/services/sai_gateway` reads it).

WHY a standalone worker (not inside the API): pysimular drives the SimularBrowser
**macOS app** over local notifications and blocks on a Cocoa run loop for minutes —
it cannot live in a FastAPI request. So this runs on the Mac that has the app,
produces a JSON data drop, and the portable backend just reads that file. Same
ingestion boundary as the demo seed, but auto-produced instead of hand-exported.

SETUP (on the Mac that runs it):
  1. Install the SimularBrowser app: open simular-mac-agent-*.dmg, drag to
     ~/Applications, launch it once, and sign in to LinkedIn inside it.
  2. pip install pysimular              # macOS only (pulls pyobjc)
  3. python scripts/sai_fetch.py "Marketing Coordinator" --out app/data/sai_live.json
     (--app-path defaults to $SIMULAR_APP_PATH or ~/Applications/SimularBrowser.app)
  4. In backend/.env set:  SAI_DATA_PATH=app/data/sai_live.json

Output JSON shape matches app/models/report.py (Job, Mentor):
  {"jobs":[{"title","company","location","url"}],
   "mentors":[{"name","role","company","url","why"}]}
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

_DEFAULT_APP = os.path.join(os.getenv("HOME", ""), "Applications", "SimularBrowser.app")

# The agent task ("edges"): browse LinkedIn and return STRUCTURED JSON, no prose.
_QUERY = (
    "On LinkedIn, find {n_jobs} current job postings for '{target}' and {n_mentors} "
    "people in '{target}' roles who would make good mentors for someone breaking in. "
    "Return ONLY a JSON object (no commentary) of exactly this shape: "
    '{{"jobs":[{{"title":"","company":"","location":"","url":""}}],'
    '"mentors":[{{"name":"","role":"","company":"","url":"","why":""}}]}}'
)

_JOB_FIELDS = ("title", "company", "location", "url")
_MENTOR_FIELDS = ("name", "role", "company", "url", "why")


def _extract_json(responses: list[str]) -> dict:
    """Pull the JSON object out of Sai's (possibly chatty) text responses."""
    text = "\n".join(responses)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in Sai response:\n{text[:500]}")
    return json.loads(text[start : end + 1])


def fetch(target: str, *, app_path: str, n_jobs: int = 5, n_mentors: int = 3, timeout: float = 600.0) -> dict:
    """Drive Sai to gather jobs/mentors for `target`; return the ingest-ready dict."""
    try:
        from pysimular import SimularBrowser  # lazy: macOS + pysimular only
    except Exception as exc:  # pragma: no cover - env-specific
        raise SystemExit(
            f"pysimular unavailable ({exc}). On macOS run: pip install pysimular"
        )

    browser = SimularBrowser(app_path, planner_mode="s1")  # s1 = hard-working mode
    output = browser.run(_QUERY.format(target=target, n_jobs=n_jobs, n_mentors=n_mentors), timeout=timeout)
    data = _extract_json(output.get("responses", []))

    jobs = [{k: str(j.get(k, "")) for k in _JOB_FIELDS} for j in data.get("jobs", [])]
    mentors = [{k: str(m.get(k, "")) for k in _MENTOR_FIELDS} for m in data.get("mentors", [])]
    return {"jobs": jobs, "mentors": mentors}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fetch LinkedIn jobs/mentors via Sai (pysimular).")
    parser.add_argument("target", help="Target role, e.g. 'Marketing Coordinator'")
    parser.add_argument("--out", default="app/data/sai_live.json", help="Output JSON path")
    parser.add_argument("--app-path", default=os.getenv("SIMULAR_APP_PATH", _DEFAULT_APP))
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--mentors", type=int, default=3)
    args = parser.parse_args(argv)

    data = fetch(args.target, app_path=args.app_path, n_jobs=args.jobs, n_mentors=args.mentors)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {len(data['jobs'])} jobs + {len(data['mentors'])} mentors -> {out}")
    print(f"Now set SAI_DATA_PATH={out} in backend/.env")


if __name__ == "__main__":
    main()
