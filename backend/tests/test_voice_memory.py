"""Persistent voice-agent memory — append/get endpoints + the prompt recap helper."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.services.voice_memory import summarize_for_prompt

client = TestClient(app)


def test_memory_append_requires_fields():
    assert client.post("/voice-agent/memory", json={"user_id": "vm1"}).status_code == 400
    assert client.post("/voice-agent/memory", json={"content": "hi"}).status_code == 400


def test_memory_roundtrip_via_endpoints():
    uid = "vm-" + uuid.uuid4().hex[:8]  # fresh user so Redis persistence can't skew the count
    client.post("/voice-agent/memory", json={"user_id": uid, "role": "user", "content": "How do I get a CDL?"})
    client.post("/voice-agent/memory", json={"user_id": uid, "role": "assistant", "content": "Start with a permit."})
    body = client.get(f"/voice-agent/memory/{uid}").json()
    assert body["count"] == 2
    assert body["turns"][0] == {"role": "user", "content": "How do I get a CDL?"}
    assert body["turns"][1]["role"] == "assistant"


def test_summarize_for_prompt_includes_history():
    recap = summarize_for_prompt(
        [{"role": "user", "content": "Ask about CDL"}, {"role": "assistant", "content": "Sure"}]
    )
    assert "CDL" in recap
    assert "User:" in recap and "You:" in recap


def test_summarize_for_prompt_empty_is_blank():
    assert summarize_for_prompt([]) == ""
