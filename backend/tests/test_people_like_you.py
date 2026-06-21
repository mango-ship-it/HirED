"""'People like you' — vector-cohort endpoint contract.

The endpoint must return a well-formed payload whether or not the RedisVL profile index
is up (it depends on Redis + the background build, which may or may not be ready in a
given env), and 404 for an unknown user. The live KNN ranking is verified against real Redis.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.services.store import save_profile

client = TestClient(app)


def test_people_like_you_404_for_unknown_user():
    assert client.get("/people-like-you/nope-nobody-here").status_code == 404


def test_people_like_you_returns_valid_shape():
    # Inject a profile directly (deterministic — avoids the persistent score cache that can
    # skip save_profile on a hit). Whether or not the vector index is up in this env, the
    # endpoint must return a well-formed payload (never a 500), with count == len(peers).
    asyncio.run(
        save_profile(
            "ply1",
            {
                "user_id": "ply1",
                "target": {"type": "role", "value": "Data Analyst"},
                "score": 61,
                "missing_skills": ["SQL", "Tableau", "statistics"],
            },
        )
    )
    body = client.get("/people-like-you/ply1").json()
    assert isinstance(body["available"], bool)
    assert isinstance(body["peers"], list)
    assert body["count"] == len(body["peers"])
    if body["available"]:
        for peer in body["peers"]:
            assert {"target", "score", "shared_gaps", "similarity"} <= peer.keys()
    else:
        assert body["count"] == 0
