"""Live readiness percentile via Redis sorted sets — slug, seed distribution, monotonicity."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.services import leaderboard as lb

client = TestClient(app)


def test_key_slug():
    assert lb._key("Registered Nurse") == "readiness:registered-nurse"
    assert lb._key("C++ Developer!!") == "readiness:c-developer"
    assert lb._key("") == "readiness:general"


def test_seed_distribution_is_reproducible_and_bounded():
    seed = lb._seed_for("readiness:test-role")
    assert len(seed) == lb._SEED_COUNT
    assert all(10 <= v <= 95 for v in seed.values())
    assert lb._seed_for("readiness:test-role") == seed  # deterministic per role


def test_benchmark_percentile_is_monotonic_in_score():
    # A fresh role seeds its own synthetic cohort; a high score must rank >= a low score.
    role = {"type": "role", "value": "Synthetic Role " + uuid.uuid4().hex[:6]}
    high = client.post("/benchmark", json={"user_id": "hi-" + uuid.uuid4().hex[:4], "score": 90, "target": role}).json()
    low = client.post("/benchmark", json={"user_id": "lo-" + uuid.uuid4().hex[:4], "score": 20, "target": role}).json()
    assert 1 <= high["percentile"] <= 99
    assert 1 <= low["percentile"] <= 99
    assert high["percentile"] >= low["percentile"]
