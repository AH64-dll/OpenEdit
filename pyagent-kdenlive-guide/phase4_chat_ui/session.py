"""Session state: chat history, pending plan, and cached project state."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


import os
import json
import uuid
from pathlib import Path
import time
import re
import logging

logger = logging.getLogger(__name__)

MAX_HISTORY = 500

DEFAULT_APP = "piagent"
DEFAULT_MODEL = ""

def _validate_session_id(session_id: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", session_id))



@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_name: str | None = None
    timestamp: float = 0.0
    images: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "tool_name": self.tool_name,
            "timestamp": self.timestamp,
            "images": [],
        }


@dataclass
class PlanCard:
    plan_id: str
    summary: str
    diff: str
    status: Literal["pending", "approved", "rejected", "applied"] = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "summary": self.summary,
            "diff": self.diff,
            "status": self.status,
        }


def get_sessions_dir() -> Path:
    d = Path(os.path.expanduser("~/.local/share/pyagent/sessions"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_sessions() -> list[dict[str, Any]]:
    sessions = []
    directory = get_sessions_dir()
    for item in directory.glob("*.json"):
        session_id = item.stem
        if not _validate_session_id(session_id):
            continue
        try:
            with open(item, "r", encoding="utf-8") as f:
                data = json.load(f)
            sessions.append({
                "session_id": data["session_id"],
                "name": data.get("name", data["session_id"]),
                "project": data.get("project", ""),
                "last_modified": data.get("last_modified", 0.0),
            })
        except Exception:
            pass
    sessions.sort(key=lambda x: x["last_modified"], reverse=True)
    return sessions


class Session:
    """Persistent chat session for one project.

    Holds the chat history (user / assistant / tool messages), at most one
    pending plan awaiting approval, and the most recent project-state snapshot.
    """

    def __init__(
        self,
        session_id: str | None = None,
        name: str | None = None,
        app: str | None = None,
        model: str | None = None,
        project: str | None = None,
    ) -> None:
        self.session_id = session_id or f"pyagent-chat-{uuid.uuid4().hex[:12]}"
        self.name = name or self.session_id
        self.app: str = app or DEFAULT_APP
        self.model: str = model or DEFAULT_MODEL
        self.project = project or ""
        self.history: list[ChatMessage] = []
        self.pending_plan: PlanCard | None = None
        self.last_project_state: dict | None = None
        self.last_modified: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "app": self.app,
            "model": self.model,
            "project": self.project,
            "history": [m.to_dict() for m in self.history],
            "pending_plan": self.pending_plan.to_dict() if self.pending_plan else None,
            "last_modified": self.last_modified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        s = cls(
            session_id=data["session_id"],
            name=data.get("name"),
            app=data.get("app", DEFAULT_APP),
            model=data.get("model", DEFAULT_MODEL),
            project=data.get("project"),
        )
        s.last_modified = data.get("last_modified", 0.0)
        s.history = []
        for m in data.get("history", []):
            s.history.append(ChatMessage(
                role=m["role"],
                content=m["content"],
                tool_name=m.get("tool_name"),
                timestamp=m.get("timestamp", 0.0),
                images=m.get("images", []),
            ))
        pp = data.get("pending_plan")
        if pp:
            s.pending_plan = PlanCard(
                plan_id=pp["plan_id"],
                summary=pp["summary"],
                diff=pp["diff"],
                status=pp.get("status", "pending"),
            )
        return s

    def save(self) -> None:
        if not _validate_session_id(self.session_id):
            logger.warning(f"Invalid session_id rejected in save: {self.session_id}")
            return
        
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

        self.last_modified = time.time()
        path = get_sessions_dir() / f"{self.session_id}.json"
        tmp_path = path.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            os.replace(str(tmp_path), str(path))
        except Exception as e:
            logger.warning(f"Failed to save session {self.session_id}: {e}")
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    @classmethod
    def load(cls, session_id: str) -> Session | None:
        if not _validate_session_id(session_id):
            logger.warning(f"Invalid session_id rejected in load: {session_id}")
            return None
        path = get_sessions_dir() / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load session {session_id}: {e}")
            return None

    # --- chat history ---------------------------------------------------

    def add_user_message(self, text: str, images: list[str] | None = None) -> None:
        self.history.append(
            ChatMessage(role="user", content=text, timestamp=time.time(), images=[])
        )
        self.save()

    def add_assistant_message(self, text: str) -> None:
        self.history.append(
            ChatMessage(role="assistant", content=text, timestamp=time.time())
        )
        self.save()

    def add_tool_event(self, tool: str, args: dict, result: Any) -> None:
        self.history.append(
            ChatMessage(
                role="tool",
                content=self._tool_text(args, result),
                tool_name=tool,
                timestamp=time.time(),
            )
        )
        self.save()

    @staticmethod
    def _tool_text(args: dict, result: Any) -> str:
        text = "args: " + json_dumps(args)
        if result is not None:
            text += "\nresult: " + json_dumps(result)
        return text

    def history_dicts(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.history]

    # --- plan state -----------------------------------------------------

    def set_pending_plan(self, plan: PlanCard) -> None:
        self.pending_plan = plan
        self.save()

    def resolve_plan(self, decision: Literal["approved", "rejected"]) -> None:
        if self.pending_plan is None:
            return
        self.pending_plan.status = decision
        self.save()

    def clear_pending_plan(self) -> None:
        self.pending_plan = None
        self.save()

    # --- project state --------------------------------------------------

    def set_project_state(self, state: dict) -> None:
        self.last_project_state = state


def json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, default=str)
    except (TypeError, ValueError):
        return str(obj)
