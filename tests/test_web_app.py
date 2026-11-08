import json
import uuid

from fastapi.testclient import TestClient

from agents.conversation_context import ConversationState
from web_app import _sessions, app


def test_chat_endpoint_uses_orchestrator_and_opt_in_profile_storage(
        tmp_path, monkeypatch):
    monkeypatch.setattr("web_app.SESSION_DIR", tmp_path)
    session_id = str(uuid.uuid4())
    _sessions.pop(session_id, None)
    observed = {}

    def fake_ask_coach(message, *, state):
        observed["message"] = message
        observed["share_profile_context"] = state.share_profile_context
        observed["share_medical_context"] = state.share_medical_context
        state.profile["weight_kg"] = 70
        state.remember_turn(message, ["diet"])
        state.save()
        return {
            "answer": "Here is a balanced meal idea.",
            "agents_used": ["diet"],
            "sources": [{"source": "nutrition.pdf", "page": 2}],
            "urgent": False,
        }

    monkeypatch.setattr("web_app.ask_coach", fake_ask_coach)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={
            "session_id": session_id,
            "message": "Suggest a balanced meal.",
            "persist_profile": True,
            "share_profile_context": True,
            "share_medical_context": False,
        })

    assert response.status_code == 200
    assert response.json()["answer"] == "Here is a balanced meal idea."
    assert "agents_used" not in response.json()
    assert "sources" not in response.json()
    assert observed == {
        "message": "Suggest a balanced meal.",
        "share_profile_context": True,
        "share_medical_context": False,
    }
    saved_file = tmp_path / f"{session_id}.json"
    saved = json.loads(saved_file.read_text(encoding="utf-8"))
    assert saved["profile"]["weight_kg"] == 70
    assert "Suggest a balanced meal" not in saved_file.read_text(encoding="utf-8")
    _sessions.pop(session_id, None)


def test_disabling_persistence_removes_saved_profile(tmp_path, monkeypatch):
    monkeypatch.setattr("web_app.SESSION_DIR", tmp_path)
    session_id = str(uuid.uuid4())
    _sessions.pop(session_id, None)
    path = tmp_path / f"{session_id}.json"
    ConversationState(path).save()
    assert path.exists()

    with TestClient(app) as client:
        response = client.post("/api/privacy", json={
            "session_id": session_id,
            "persist_profile": False,
            "share_profile_context": False,
            "share_medical_context": False,
        })

    assert response.status_code == 200
    assert not path.exists()
    _sessions.pop(session_id, None)


def test_homepage_and_health_endpoint_are_available():
    with TestClient(app) as client:
        homepage = client.get("/")
        health = client.get("/api/health")
        health_alias = client.get("/health")

    assert homepage.status_code == 200
    assert "Aabvita" in homepage.text
    assert "Your Health. Intelligently Guided." in homepage.text
    assert health.json() == {"status": "ok"}
    assert health_alias.status_code == 200
    assert health_alias.json() == health.json()
