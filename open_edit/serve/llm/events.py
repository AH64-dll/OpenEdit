"""StreamEvent contract — the one event shape every provider yields."""
from __future__ import annotations

from typing import Any, Literal, TypedDict


class StreamEvent(TypedDict, total=False):
    """One event yielded by :func:`stream_chat`.

    Variants (the ``type`` field discriminates):
    - ``"text_delta"`` — assistant text delta. Carries ``text: str``.
    - ``"tool_use"``   — a tool invocation request. Carries ``id: str``,
      ``name: str``, ``input: dict``.
    - ``"tool_result"``— the result of a tool call. Carries ``name: str``,
      ``result: dict``. (Only emitted by the pi provider, which executes
      tools in its TS extension; other providers don't re-emit this.)
    - ``"usage"``      — token / cost accounting. Carries ``tokens: int``,
      ``cost_usd: float``, ``usage: dict``, ``source: str``.
    - ``"done"``       — terminal event. Carries ``stop_reason: str``.
    - ``"error"``      — misconfiguration or transport error. Carries
      ``message: str``.

    Total=False because each variant carries a different subset; the
    ``type`` field is the discriminant.
    """
    type: Literal[
        "text_delta", "tool_use", "tool_result",
        "usage", "done", "error",
    ]
    text: str
    id: str
    name: str
    input: dict
    result: dict
    tokens: int
    cost_usd: float
    usage: dict
    source: str
    stop_reason: str
    message: str


def _coerce_event(raw: dict[str, Any]) -> StreamEvent:
    if not isinstance(raw, dict) or "type" not in raw:
        raise ValueError("StreamEvent must contain a 'type' field")
    out = dict(raw)
    etype = out.get("type")
    if etype == "text_delta" and "text" not in out:
        out["text"] = ""
    elif etype == "tool_use":
        out.setdefault("id", "")
        out.setdefault("name", "")
        out.setdefault("input", {})
    elif etype == "tool_result":
        out.setdefault("name", "")
        out.setdefault("result", {})
    elif etype == "done" and "stop_reason" not in out:
        out["stop_reason"] = "end_turn"
    return out  # type: ignore[return-value]
