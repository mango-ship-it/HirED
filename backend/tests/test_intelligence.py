"""Tests for Deepgram Text Intelligence endpoint + parser (hermetic — key cleared)."""
from fastapi.testclient import TestClient

from app.main import app
from app.routes.voice import _profile_text
from app.services.deepgram_service import _parse_intelligence

client = TestClient(app)


def test_intelligence_requires_text_or_user():
    assert client.post("/intelligence", json={}).status_code == 400


def test_intelligence_without_deepgram_key_is_graceful():
    response = client.post("/intelligence", json={"text": "I am a Python developer seeking a data role."})
    assert response.status_code == 200
    assert response.json()["configured"] is False  # no key in tests


def test_parse_intelligence_defensive_on_garbage():
    out = _parse_intelligence(object())  # no model_dump/to_dict -> graceful empty
    assert out == {"summary": "", "topics": [], "intents": [], "sentiment": {}}


def test_parse_intelligence_extracts_fields():
    class Resp:
        def model_dump(self):
            return {
                "results": {
                    "summary": {"text": "A Python developer."},
                    "topics": {"segments": [{"topics": [{"topic": "technical skills"}]}]},
                    "intents": {"segments": [{"intents": [{"intent": "find a job"}]}]},
                    "sentiments": {"average": {"sentiment": "positive", "sentiment_score": 0.4}},
                }
            }

    out = _parse_intelligence(Resp())
    assert out["summary"] == "A Python developer."
    assert "technical skills" in out["topics"]
    assert "find a job" in out["intents"]
    assert out["sentiment"]["label"] == "positive"


def test_profile_text_flattens_record():
    text = _profile_text(
        {"target": {"value": "Data Analyst"}, "matched_skills": ["SQL"], "missing_skills": ["Tableau"]}
    )
    assert "Data Analyst" in text and "SQL" in text and "Tableau" in text
