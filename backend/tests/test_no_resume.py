"""No-resume / empty-resume robustness (from the no-resume audit).

Covers the shared content floor (a near-empty input never gets a fake score), the
explicit has_resume signal on /score, and GET /profile normalizing legacy records
(saved before resume_text existed) so the frontend always gets a consistent shape
to gate the side-by-side resume view on.
"""

from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from app.main import app
from app.services.resume_guard import has_usable_resume, resume_word_count
from app.services.store import save_profile

client = TestClient(app)

_TARGET = json.dumps({"type": "role", "value": "Data Analyst"})


# --- the shared guard ------------------------------------------------------- #


def test_resume_guard_rejects_near_empty():
    for junk in ["", "   ", ".", "1", "N/A", "—", "•", "  .  "]:
        assert not has_usable_resume(junk), junk
    assert resume_word_count(".") == 0


def test_resume_guard_accepts_real_resume():
    assert has_usable_resume("Experienced bus driver with a clean record")
    assert has_usable_resume("Cook 5 years restaurant")  # terse but real


# --- /score content floor --------------------------------------------------- #


def test_score_rejects_near_empty_resume():
    response = client.post(
        "/score", data={"user_id": "ne1", "target": _TARGET, "resume_text": "."}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"


def test_score_sets_has_resume_true_for_real_resume():
    response = client.post(
        "/score",
        data={
            "user_id": "hr1",
            "target": _TARGET,
            "resume_text": "Built dashboards in Tableau and SQL. 3 years experience. BS in Statistics.",
        },
    )
    assert response.status_code == 200
    assert response.json()["has_resume"] is True


# --- /profile normalization (legacy records) -------------------------------- #


def test_profile_backfills_legacy_record_without_resume_text():
    # Simulate a profile saved BEFORE resume_text persistence: the key is absent.
    asyncio.run(
        save_profile(
            "legacy-no-resume",
            {"user_id": "legacy-no-resume", "target": {"type": "role", "value": "Cook"}, "score": 42},
        )
    )
    body = client.get("/profile/legacy-no-resume").json()
    assert body["has_resume"] is False
    assert body["resume_text"] == ""   # backfilled, never missing
    assert body["annotations"] == []   # backfilled
    assert body["score"] == 42         # original fields preserved


def test_profile_reports_has_resume_true_after_real_score():
    client.post(
        "/score",
        data={
            "user_id": "hr2",
            "target": _TARGET,
            "resume_text": "Python and SQL developer, 4 years experience, BS in Computer Science.",
        },
    )
    body = client.get("/profile/hr2").json()
    assert body["has_resume"] is True
    assert body["resume_text"]
