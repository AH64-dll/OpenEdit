"""Shared dataclasses for phase4_chat_ui.

Consolidates the small, dependency-free value types used across the chat UI
so they can be imported without pulling in session / pi-client machinery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


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


@dataclass
class PiEvent:
    """A normalized event emitted while a prompt is being processed."""
    kind: str  # "message" | "tool" | "plan" | "error" | "done"
    role: str | None = None          # for message: "user" | "assistant"
    text: str | None = None          # for message / error
    tool: str | None = None          # for tool
    args: dict | None = None         # for tool
    result: Any | None = None        # for tool
    error: str | None = None         # for tool / error
    cost: float | None = None         # USD spent this event (from pi usage.cost.total)
