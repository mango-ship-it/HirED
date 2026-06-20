"""Assemble the detailed report + slide deck from scored data (+ Sai jobs/mentors).

Templated and deterministic — **no API spend**. (A cheap-Claude 'polish' pass over
the prose can be added later behind a flag using settings.gen_model; intentionally
not wired so the default path costs nothing.) Brand voice: reliable and kind.
"""

from __future__ import annotations

from app.models.report import ReportRequest, ReportResponse, Slide
from app.services import sai_gateway

_LABELS = {
    "skills_match": "Skills Match",
    "quantified_achievements": "Quantified Impact",
    "experience": "Relevant Experience",
    "education": "Education",
    "clarity": "Clarity & Communication",
}

_STRONG = 70  # >= is a strength
_WEAK = 60  # < is a gap worth calling out


def _label(key: str) -> str:
    return _LABELS.get(key, key.replace("_", " ").title())


def _strengths(req: ReportRequest) -> list[str]:
    items = sorted(req.categories.items(), key=lambda kv: kv[1].score, reverse=True)
    return [f"{_label(k)} ({c.score}/100)" for k, c in items if c.score >= _STRONG][:3]


def _weaknesses(req: ReportRequest) -> list[str]:
    items = sorted(req.categories.items(), key=lambda kv: kv[1].score)
    return [f"{_label(k)} ({c.score}/100)" for k, c in items if c.score < _WEAK][:3]


def _next_steps(req: ReportRequest) -> list[str]:
    steps = [lesson.action for lesson in req.lessons if lesson.action][:3]
    if steps:
        return steps
    return [f"Add evidence of {skill} to your resume." for skill in req.missing_skills[:3]]


def _summary(req: ReportRequest, strengths: list[str], weaknesses: list[str]) -> str:
    target = req.target.value
    parts = [f"You're at {req.score}/100 for {target}."]
    if req.percentile is not None:
        parts.append(f"That puts you ahead of about {req.percentile}% of people aiming for this.")
    if strengths:
        parts.append(f"Your strongest area is {strengths[0].split(' (')[0]} — lead with it.")
    if weaknesses:
        parts.append(
            f"The fastest way to move your number is {weaknesses[0].split(' (')[0]}; "
            "we've laid out exactly how below."
        )
    elif req.missing_skills:
        parts.append(f"Closing the gap on {req.missing_skills[0]} is your highest-leverage next step.")
    return " ".join(parts)


def _slides(
    req: ReportRequest,
    summary: str,
    strengths: list[str],
    weaknesses: list[str],
    next_steps: list[str],
    jobs,
    mentors,
) -> list[Slide]:
    target = req.target.value
    slides: list[Slide] = []

    def add(title: str, body: str, notes: str) -> None:
        slides.append(Slide(index=len(slides), title=title, body=body, speaker_notes=notes))

    add(
        "Your readiness",
        f"{req.score}/100 for {target}",
        f"Here's where you stand for {target}: {req.score} out of 100. {summary}",
    )
    if req.categories:
        body = " · ".join(f"{_label(k)}: {c.score}" for k, c in req.categories.items())
        add("The breakdown", body, "Here's how that score splits across the categories that matter. " + body)
    if strengths:
        add("What's working", "\n".join(f"• {s}" for s in strengths),
            "Let's start with your strengths. " + "; ".join(strengths) + ".")
    # One slide per gap lesson — the teaching core.
    for lesson in req.lessons[:3]:
        add(
            _label(lesson.category),
            f"{lesson.principle}\n\nExample: {lesson.example}\n\nDo this: {lesson.action}",
            f"{lesson.principle} For example: {lesson.example} Your next step: {lesson.action}",
        )
    if req.percentile is not None:
        add(
            "How you compare",
            f"Ahead of {req.percentile}% of candidates for {target}."
            + (f"\nWhat the top tier has that you don't: {', '.join(req.missing_skills[:4])}." if req.missing_skills else ""),
            f"Compared to people who landed {target}, you're ahead of {req.percentile} percent.",
        )
    if req.resources:
        body = "\n".join(f"• {r.name} — {r.description}" for r in req.resources[:4])
        add("Free resources to close the gaps", body, "These are free ways to close those gaps. " + body)
    if jobs:
        body = "\n".join(f"• {j.title} — {j.company} ({j.location})" for j in jobs[:4])
        add("Roles you could apply to now", body, "Here are real openings that fit where you are. " + body)
    if mentors:
        body = "\n".join(f"• {m.name}, {m.role} at {m.company} — {m.why}" for m in mentors[:3])
        add("People worth reaching out to", body, "And a few people worth a message. " + body)
    if next_steps:
        add("Your next steps", "\n".join(f"{i + 1}. {s}" for i, s in enumerate(next_steps)),
            "To wrap up, your concrete next steps: " + "; ".join(next_steps) + ".")
    return slides


def build_report(req: ReportRequest) -> ReportResponse:
    """Build the full report + narrated slide deck (templated, no API spend)."""
    strengths = _strengths(req)
    weaknesses = _weaknesses(req)
    next_steps = _next_steps(req)
    summary = _summary(req, strengths, weaknesses)
    jobs = sai_gateway.load_jobs(req.target.value)
    mentors = sai_gateway.load_mentors(req.target.value)
    slides = _slides(req, summary, strengths, weaknesses, next_steps, jobs, mentors)
    return ReportResponse(
        summary=summary,
        strengths=strengths,
        weaknesses=weaknesses,
        next_steps=next_steps,
        jobs=jobs,
        mentors=mentors,
        slides=slides,
    )
