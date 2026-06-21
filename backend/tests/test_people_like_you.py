"""'People like you' — vector-cohort endpoint + graceful degradation.

The RedisVL profile index needs Redis; the test env has none, so these verify the
endpoint returns a clean `available:false` shape (never a 500) when the index is down.
The live KNN ranking is verified separately against real Redis.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_TARGET = json.dumps({"type": "role", "value": "Data Analyst"})


def test_people_like_you_404_for_unknown_user():
    assert client.get("/people-like-you/nope-nobody-here").status_code == 404


def test_people_like_you_degrades_gracefully_without_index():
    # A profile exists (scored), but without Redis the vector index is unavailable — the
    # endpoint must return a clean empty/available:false payload, not a 500.
    client.post(
        "/score",
        data={
            "user_id": "ply1",
            "target": _TARGET,
            "resume_text": "Python and SQL developer, 4 years experience, BS in Computer Science.",
        },
    )
    body = client.get("/people-like-you/ply1").json()
    assert body["available"] is False
    assert body["count"] == 0
    assert body["peers"] == []
