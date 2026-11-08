"""Local web interface for the Aabvita multi-agent orchestrator."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents.conversation_context import ConversationState
from agents.orchestrator import ask_coach

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
SESSION_DIR = ROOT / "data" / "user_sessions"

app = FastAPI(title="Aabvita", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@dataclass
class SessionEntry:
    state: ConversationState
    lock: threading.Lock = field(default_factory=threading.Lock)


_sessions: dict[str, SessionEntry] = {}
_sessions_lock = threading.Lock()


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=36, max_length=36)
    message: str = Field(min_length=1, max_length=4000)
    persist_profile: bool = False
    share_profile_context: bool = False
    share_medical_context: bool = False


class ResetRequest(BaseModel):
    session_id: str = Field(min_length=36, max_length=36)


class PrivacyRequest(ResetRequest):
    persist_profile: bool = False
    share_profile_context: bool = False
    share_medical_context: bool = False


def _session_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid session ID") from exc


def _get_entry(session_id: str, persist_profile: bool) -> SessionEntry:
    session_uuid = _session_uuid(session_id)
    with _sessions_lock:
        entry = _sessions.get(str(session_uuid))
        if entry is None:
            path = SESSION_DIR / f"{session_uuid}.json"
            if not persist_profile and path.exists():
                path.unlink()
            path = SESSION_DIR / f"{session_uuid}.json" if persist_profile else None
            entry = SessionEntry(ConversationState(path))
            _sessions[str(session_uuid)] = entry
        elif persist_profile and entry.state.path is None:
            path = SESSION_DIR / f"{session_uuid}.json"
            previous = entry.state
            restored = ConversationState(path)
            restored.profile.update(previous.profile)
            for name in (
                "pending_food", "last_topic", "last_subject", "last_agents",
                "recent_topics", "last_question",
            ):
                value = getattr(previous, name)
                if value:
                    setattr(restored, name, value)
            entry.state = restored
        elif not persist_profile:
            path = SESSION_DIR / f"{session_uuid}.json"
            if path.exists():
                path.unlink()
            entry.state.path = None
        return entry


@app.get("/")
def home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message must not be empty")

    entry = _get_entry(request.session_id, request.persist_profile)
    with entry.lock:
        entry.state.share_profile_context = request.share_profile_context
        entry.state.share_medical_context = request.share_medical_context
        result = ask_coach(message, state=entry.state)

    return {
        "answer": result["answer"],
        "urgent": result.get("urgent", False),
    }


@app.post("/api/privacy")
def update_privacy(request: PrivacyRequest) -> dict[str, str]:
    entry = _get_entry(request.session_id, request.persist_profile)
    with entry.lock:
        entry.state.share_profile_context = request.share_profile_context
        entry.state.share_medical_context = request.share_medical_context
    return {"status": "updated"}


@app.post("/api/reset")
def reset(request: ResetRequest) -> dict[str, str]:
    session_uuid = _session_uuid(request.session_id)
    entry = _get_entry(str(session_uuid), persist_profile=False)
    with entry.lock:
        entry.state.clear()
    return {"status": "reset"}
