"""Session state: chat history, pending plan, and cached project state."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_name: str | None = None
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "tool_name": self.tool_name,
            "timestamp": self.timestamp,
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


class Session:
    """In-memory chat session for one project.

    Holds the chat history (user / assistant / tool messages), at most one
    pending plan awaiting approval, and the most recent project-state snapshot.
    """

    def __init__(self) -> None:
        self.history: list[ChatMessage] = []
        self.pending_plan: PlanCard | None = None
        self.last_project_state: dict | None = None

    # --- chat history ---------------------------------------------------

    def add_user_message(self, text: str) -> None:
        import time
        self.history.append(
            ChatMessage(role="user", content=text, timestamp=time.time())
        )

    def add_assistant_message(self, text: str) -> None:
        import time
        self.history.append(
            ChatMessage(role="assistant", content=text, timestamp=time.time())
        )

    def add_tool_event(self, tool: str, args: dict, result: Any) -> None:
        import time
        self.history.append(
            ChatMessage(
                role="tool",
                content=self._tool_text(args, result),
                tool_name=tool,
                timestamp=time.time(),
            )
        )

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

    def resolve_plan(self, decision: Literal["approved", "rejected"]) -> None:
        if self.pending_plan is None:
            return
        self.pending_plan.status = decision
        # Keep it visible briefly; app layer decides when to clear.

    def clear_pending_plan(self) -> None:
        self.pending_plan = None

    # --- project state --------------------------------------------------

    def set_project_state(self, state: dict) -> None:
        self.last_project_state = state


def json_dumps(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, default=str)
    except (TypeError, ValueError):
        return str(obj)
